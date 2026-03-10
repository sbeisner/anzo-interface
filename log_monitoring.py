"""
Log-Based Monitoring for Altair Graph Studio (Anzo)

Provides two capabilities:

1. **LDAP Exception Detection** — scans Anzo server logs for LDAP-related
   exceptions and error messages within a defined time window.

2. **AnzoGraph User Activity Monitoring** — counts and lists unique users
   who submitted queries to AnzoGraph within a defined time window, by
   parsing Anzo server logs.

Supports reading logs:
- **Locally** — when log files are mounted or accessible on the running host.
- **Remotely via SSH** — requires ``paramiko``: ``pip install paramiko``

Default Anzo log locations (5.4+)::

    /opt/Anzo/Server/logs/AnzoServer.log      # main server log
    /opt/Anzo/Server/logs/AnzoServer.log.1    # rotated log (previous day)

Anzo uses Log4j2 with the format::

    YYYY-MM-DD HH:mm:ss,SSS LEVEL [thread] logger - message

Example entries::

    2025-03-10 14:23:45,123 ERROR [ldap-pool-1] c.c.ldap.LdapConn - javax.naming.CommunicationException
    2025-03-10 14:25:01,456 INFO  [http-nio-443-1] AUDIT: user=jsmith action=SPARQL_QUERY datasource=AnzoGraph
"""

import io
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional SSH support
# ---------------------------------------------------------------------------

try:
    import paramiko
    _PARAMIKO_AVAILABLE = True
except ImportError:
    _PARAMIKO_AVAILABLE = False


# ---------------------------------------------------------------------------
# Log line timestamp parsing
# ---------------------------------------------------------------------------

# Matches Log4j2 timestamps: "2025-03-10 14:23:45,123"
_LOG4J_TIMESTAMP_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}'
)
_LOG4J_TIMESTAMP_FMT = '%Y-%m-%d %H:%M:%S'


def _parse_log_timestamp(line: str) -> Optional[datetime]:
    """Extract the Log4j2 timestamp from the start of a log line."""
    m = _LOG4J_TIMESTAMP_RE.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), _LOG4J_TIMESTAMP_FMT)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Log file reading — local and remote
# ---------------------------------------------------------------------------

def _read_local_log(path: str) -> list[str]:
    """Read a local log file and return its lines."""
    return Path(path).read_text(errors='replace').splitlines()


def _read_remote_log(
    ssh_host: str,
    ssh_user: str,
    log_path: str,
    ssh_key_path: Optional[str] = None,
    ssh_password: Optional[str] = None,
    ssh_port: int = 22,
) -> list[str]:
    """
    Read a remote log file via SSH using paramiko.

    Args:
        ssh_host: Hostname or IP of the Anzo server.
        ssh_user: SSH username (e.g. ``foundry``).
        log_path: Absolute path to the log file on the remote host.
        ssh_key_path: Path to private key file. Uses SSH agent/default keys if omitted.
        ssh_password: SSH password (used instead of key if provided).
        ssh_port: SSH port (default: 22).

    Returns:
        List of log lines.

    Raises:
        ImportError: If paramiko is not installed.
        paramiko.SSHException: On SSH connection or auth failure.
    """
    if not _PARAMIKO_AVAILABLE:
        raise ImportError(
            "paramiko is required for remote log access. Install it with: pip install paramiko"
        )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs = dict(hostname=ssh_host, port=ssh_port, username=ssh_user)
    if ssh_password:
        connect_kwargs['password'] = ssh_password
    elif ssh_key_path:
        connect_kwargs['key_filename'] = ssh_key_path

    try:
        client.connect(**connect_kwargs)
        sftp = client.open_sftp()
        with sftp.open(log_path, 'r') as f:
            content = io.TextIOWrapper(f, encoding='utf-8', errors='replace').read()
        return content.splitlines()
    finally:
        client.close()


def _collect_lines(
    log_paths: list[str],
    ssh_host: Optional[str] = None,
    ssh_user: Optional[str] = None,
    ssh_key_path: Optional[str] = None,
    ssh_password: Optional[str] = None,
    ssh_port: int = 22,
) -> list[str]:
    """Collect lines from one or more log files (local or remote)."""
    all_lines: list[str] = []
    for path in log_paths:
        try:
            if ssh_host:
                lines = _read_remote_log(
                    ssh_host=ssh_host,
                    ssh_user=ssh_user,
                    log_path=path,
                    ssh_key_path=ssh_key_path,
                    ssh_password=ssh_password,
                    ssh_port=ssh_port,
                )
            else:
                lines = _read_local_log(path)
            all_lines.extend(lines)
            logger.debug(f"Read {len(lines)} lines from {path}")
        except FileNotFoundError:
            logger.warning(f"Log file not found, skipping: {path}")
        except Exception as e:
            logger.warning(f"Could not read {path}: {e}")
    return all_lines


# ---------------------------------------------------------------------------
# LDAP Exception Detection
# ---------------------------------------------------------------------------

# Patterns that indicate LDAP-related failures in Anzo's log output.
# These cover Java LDAP stack traces, Anzo's own LDAP classes, and generic
# LDAP error strings that appear in Log4j output.
_LDAP_EXCEPTION_PATTERNS: list[re.Pattern] = [
    re.compile(r'javax\.naming\.(NamingException|CommunicationException|AuthenticationException)', re.IGNORECASE),
    re.compile(r'com\.unboundid\.ldap', re.IGNORECASE),
    re.compile(r'ldap.*(exception|error|fail|timeout|refused|unreachable)', re.IGNORECASE),
    re.compile(r'(error|exception|fail).*(ldap)', re.IGNORECASE),
    re.compile(r'LdapException', re.IGNORECASE),
    re.compile(r'LDAP server.*unavailable', re.IGNORECASE),
    re.compile(r'bind.*failed.*ldap|ldap.*bind.*failed', re.IGNORECASE),
]


@dataclass
class LdapExceptionReport:
    """
    Results of scanning Anzo logs for LDAP exceptions.

    Attributes:
        exception_count: Total number of LDAP exception lines detected.
        exceptions: List of individual exception entries (timestamp + line).
        window_start: Start of the scanned time window.
        window_end: End of the scanned time window (typically ``datetime.now()``).
        log_paths: Log files that were scanned.
        scan_timestamp: When the scan was performed.
    """
    exception_count: int
    exceptions: list[dict]
    window_start: datetime
    window_end: datetime
    log_paths: list[str]
    scan_timestamp: datetime = field(default_factory=datetime.now)


def scan_ldap_exceptions(
    window_minutes: int = 60,
    log_paths: Optional[list[str]] = None,
    ssh_host: Optional[str] = None,
    ssh_user: Optional[str] = None,
    ssh_key_path: Optional[str] = None,
    ssh_password: Optional[str] = None,
    ssh_port: int = 22,
    extra_patterns: Optional[list[re.Pattern]] = None,
) -> LdapExceptionReport:
    """
    Scan Anzo server logs for LDAP-related exceptions within a time window.

    Args:
        window_minutes: How far back to look in the logs (default: 60 minutes).
        log_paths: List of absolute log file paths to scan. Defaults to the
            standard Anzo 5.4+ log location (current log + one rotated file).
        ssh_host: If set, read log files from this remote host over SSH.
        ssh_user: SSH username (required when ``ssh_host`` is set).
        ssh_key_path: Path to SSH private key file.
        ssh_password: SSH password (alternative to key).
        ssh_port: SSH port (default: 22).
        extra_patterns: Additional compiled ``re.Pattern`` objects to match
            against log lines, in addition to the built-in LDAP patterns.

    Returns:
        :class:`LdapExceptionReport` with matching lines and counts.

    Example — local logs::

        report = scan_ldap_exceptions(window_minutes=30)
        if report.exception_count > 0:
            print(f"Found {report.exception_count} LDAP exceptions in the last 30 minutes")
            for exc in report.exceptions:
                print(f"  [{exc['timestamp']}] {exc['message']}")

    Example — remote logs via SSH::

        report = scan_ldap_exceptions(
            window_minutes=60,
            ssh_host="192.168.5.96",
            ssh_user="foundry",
            ssh_key_path="~/.ssh/devops_id_rsa",
        )
    """
    if log_paths is None:
        log_paths = [
            '/opt/Anzo/Server/logs/AnzoServer.log',
            '/opt/Anzo/Server/logs/AnzoServer.log.1',
        ]

    patterns = _LDAP_EXCEPTION_PATTERNS + (extra_patterns or [])

    window_end = datetime.now()
    window_start = window_end - timedelta(minutes=window_minutes)

    all_lines = _collect_lines(
        log_paths=log_paths,
        ssh_host=ssh_host,
        ssh_user=ssh_user,
        ssh_key_path=ssh_key_path,
        ssh_password=ssh_password,
        ssh_port=ssh_port,
    )

    exceptions: list[dict] = []
    current_ts: Optional[datetime] = None

    for line in all_lines:
        # Update current timestamp when the line has one
        ts = _parse_log_timestamp(line)
        if ts is not None:
            current_ts = ts

        # Skip lines outside the time window
        if current_ts is None or current_ts < window_start or current_ts > window_end:
            continue

        # Check against LDAP patterns
        if any(p.search(line) for p in patterns):
            exceptions.append({
                'timestamp': current_ts.isoformat(),
                'message': line.strip(),
            })

    logger.info(
        f"LDAP exception scan: {len(exceptions)} exception(s) found in last {window_minutes} minutes"
    )

    return LdapExceptionReport(
        exception_count=len(exceptions),
        exceptions=exceptions,
        window_start=window_start,
        window_end=window_end,
        log_paths=log_paths,
    )


# ---------------------------------------------------------------------------
# AnzoGraph User Activity Monitoring
# ---------------------------------------------------------------------------

# Patterns that identify the authenticated user in Anzo log lines.
# Anzo logs SPARQL requests with the username in several formats depending
# on the component (REST API access log, audit logger, AnzoGraph proxy).
_USER_PATTERNS: list[re.Pattern] = [
    re.compile(r'\buser[=:](\S+)', re.IGNORECASE),
    re.compile(r'\bprincipal[=:](\S+)', re.IGNORECASE),
    re.compile(r'\busername[=:](\S+)', re.IGNORECASE),
    re.compile(r'Authenticated as[:\s]+(\S+)', re.IGNORECASE),
]

# Only count lines that reference AnzoGraph (to filter out non-AZG activity).
_ANZOGRAPH_PATTERNS: list[re.Pattern] = [
    re.compile(r'anzograph', re.IGNORECASE),
    re.compile(r'graphmart', re.IGNORECASE),
    re.compile(r'/sparql/graphmart/', re.IGNORECASE),
    re.compile(r'sparql.*gqe|gqe.*sparql', re.IGNORECASE),
    re.compile(r'datasource.*AnzoGraph|AnzoGraph.*datasource', re.IGNORECASE),
]


@dataclass
class AnzoGraphUserActivityReport:
    """
    Results of scanning Anzo logs for AnzoGraph user activity.

    Attributes:
        unique_user_count: Number of distinct users who accessed AnzoGraph.
        users: Set of unique usernames observed.
        query_count: Total number of AnzoGraph query log lines matched.
        window_start: Start of the scanned time window.
        window_end: End of the scanned time window.
        log_paths: Log files that were scanned.
        scan_timestamp: When the scan was performed.
    """
    unique_user_count: int
    users: set[str]
    query_count: int
    window_start: datetime
    window_end: datetime
    log_paths: list[str]
    scan_timestamp: datetime = field(default_factory=datetime.now)


def scan_anzograph_user_activity(
    window_minutes: int = 60,
    log_paths: Optional[list[str]] = None,
    ssh_host: Optional[str] = None,
    ssh_user: Optional[str] = None,
    ssh_key_path: Optional[str] = None,
    ssh_password: Optional[str] = None,
    ssh_port: int = 22,
    extra_user_patterns: Optional[list[re.Pattern]] = None,
) -> AnzoGraphUserActivityReport:
    """
    Count unique users accessing AnzoGraph within a time window by parsing logs.

    Scans Anzo server logs for lines that reference AnzoGraph activity and
    extracts the authenticated username from each matching line. Returns
    the set of unique users and a total query count.

    Args:
        window_minutes: How far back to look in the logs (default: 60 minutes).
        log_paths: Log file paths to scan. Defaults to the standard Anzo
            5.4+ log location (current + one rotated file).
        ssh_host: Remote host to read logs from over SSH.
        ssh_user: SSH username.
        ssh_key_path: Path to SSH private key.
        ssh_password: SSH password.
        ssh_port: SSH port (default: 22).
        extra_user_patterns: Additional compiled ``re.Pattern`` objects to
            extract usernames, in addition to the built-in patterns. Each
            pattern must have one capture group containing the username.

    Returns:
        :class:`AnzoGraphUserActivityReport` with user set and counts.

    Example — local logs, last 2 hours::

        report = scan_anzograph_user_activity(window_minutes=120)
        print(f"{report.unique_user_count} user(s) accessed AnzoGraph:")
        for user in sorted(report.users):
            print(f"  {user}")

    Example — remote logs::

        report = scan_anzograph_user_activity(
            window_minutes=60,
            ssh_host="192.168.5.96",
            ssh_user="foundry",
            ssh_key_path="~/.ssh/devops_id_rsa",
        )
        print(f"Active users in last hour: {report.unique_user_count}")

    Note:
        Username extraction depends on the log format configured on your Anzo
        instance. If ``unique_user_count`` is 0 but you expect activity, check
        your log format and supply ``extra_user_patterns`` to match it.
    """
    if log_paths is None:
        log_paths = [
            '/opt/Anzo/Server/logs/AnzoServer.log',
            '/opt/Anzo/Server/logs/AnzoServer.log.1',
        ]

    user_patterns = _USER_PATTERNS + (extra_user_patterns or [])

    window_end = datetime.now()
    window_start = window_end - timedelta(minutes=window_minutes)

    all_lines = _collect_lines(
        log_paths=log_paths,
        ssh_host=ssh_host,
        ssh_user=ssh_user,
        ssh_key_path=ssh_key_path,
        ssh_password=ssh_password,
        ssh_port=ssh_port,
    )

    users: set[str] = set()
    query_count = 0
    current_ts: Optional[datetime] = None

    for line in all_lines:
        ts = _parse_log_timestamp(line)
        if ts is not None:
            current_ts = ts

        if current_ts is None or current_ts < window_start or current_ts > window_end:
            continue

        # Only process lines referencing AnzoGraph activity
        if not any(p.search(line) for p in _ANZOGRAPH_PATTERNS):
            continue

        query_count += 1

        # Extract username from line
        for pattern in user_patterns:
            m = pattern.search(line)
            if m:
                user = m.group(1).strip('",;')
                if user:
                    users.add(user)
                break

    logger.info(
        f"AnzoGraph activity scan: {query_count} log line(s), "
        f"{len(users)} unique user(s) in last {window_minutes} minutes"
    )

    return AnzoGraphUserActivityReport(
        unique_user_count=len(users),
        users=users,
        query_count=query_count,
        window_start=window_start,
        window_end=window_end,
        log_paths=log_paths,
    )


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO)
    window = int(sys.argv[1]) if len(sys.argv) > 1 else 60

    print(f"\n{'=' * 70}")
    print(f"LOG MONITORING — last {window} minutes")
    print('=' * 70)

    # LDAP exceptions
    ldap_report = scan_ldap_exceptions(window_minutes=window)
    print(f"\nLDAP Exceptions: {ldap_report.exception_count}")
    for exc in ldap_report.exceptions[:10]:
        print(f"  [{exc['timestamp']}] {exc['message'][:120]}")
    if ldap_report.exception_count > 10:
        print(f"  ... and {ldap_report.exception_count - 10} more")

    # AnzoGraph user activity
    activity_report = scan_anzograph_user_activity(window_minutes=window)
    print(f"\nAnzoGraph User Activity: {activity_report.unique_user_count} unique user(s), "
          f"{activity_report.query_count} query log lines")
    for user in sorted(activity_report.users):
        print(f"  {user}")

    print()
