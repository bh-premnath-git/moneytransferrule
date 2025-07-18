# Multi-stage build for Money Transfer Rules Engine
# Stage 1: Build dependencies and generate proto files
FROM python:3.12-slim as builder

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    build-essential \
    protobuf-compiler \
    libprotobuf-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /build

# Copy dependency files
COPY requirements.txt ./

# Upgrade pip and install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy proto files and scripts
COPY proto/ proto/
COPY scripts/ scripts/

# Make scripts executable
RUN chmod +x scripts/*.sh

# Generate proto files
RUN scripts/gen_protos.sh proto proto_gen

# Stage 2: Production image
FROM python:3.12-slim as production

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libprotobuf32 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser \
    && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    rm requirements.txt

# Copy application code
COPY app/ app/
COPY --from=builder /build/proto_gen/ proto_gen/

# Create necessary directories
RUN mkdir -p logs tmp && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV REDIS_URL=redis://redis:6379
ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV REST_PORT=8000
ENV GRPC_PORT=50051
ENV LOG_LEVEL=INFO

# Expose ports
EXPOSE 8000 50051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
echo "Starting Money Transfer Rules Engine..."\n\
python -m uvicorn app.main:app --host 0.0.0.0 --port ${REST_PORT} &\n\
python -m app.grpc_server &\n\
\n\
# Wait for any process to exit\n\
wait -n\n\
\n\
# Exit with status of process that exited first\n\
exit $?\n\
' > /app/start.sh && chmod +x /app/start.sh

# Command to run the application
CMD ["/app/start.sh"]
