FROM python:3.9-slim

# Install OpenJDK so jstat is available for JVM GC metrics.
# If you don't need /metrics/jvm, remove this block to keep the image smaller.
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-docker.txt ./
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY anzo_monitoring_service.py ./

ENV ANZO_PROCESS_NAME=AnzoLauncher \
    SERVICE_PORT=9090

EXPOSE 9090

CMD ["python3", "anzo_monitoring_service.py"]
