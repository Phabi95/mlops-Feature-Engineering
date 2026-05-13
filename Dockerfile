# --- Stage 1: Build Environment ---
# Compiles dependencies in a temporary container 
FROM python:3.11-slim AS builder
WORKDIR /app

# Install compilation tools and clean cache 
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Pre-install requirements to a portable prefix [cite: 3]
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 2: Runtime Environment ---
# Lean image for production deployment 
FROM python:3.11-slim
WORKDIR /app

# Install lightweight runtime utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Transfer compiled artifacts from builder stage 
COPY --from=builder /install /usr/local

# Security: Enforce non-root execution
RUN groupadd -r mluser && useradd -r -g mluser mluser

# Initialize persistent volumes and shared memory for metrics
RUN mkdir -p /data /app/logs /tmp/prometheus_multiproc && \
    chown -R mluser:mluser /data /app/logs /tmp/prometheus_multiproc

# Deploy application source with restricted ownership [cite: 4]
COPY --chown=mluser:mluser . .

# Performance and Monitoring Configuration
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc

USER mluser
EXPOSE 8000

# High-concurrency production server (uvloop/httptools)
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*", \
     "--no-access-log"]