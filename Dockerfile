# ==============================================================================
# Production Dockerfile for GoFloaters Invoice Parser (Native FastAPI)
# Direct in-memory Python execution with Docling & RapidOCR
# Optimized for Docker & Coolify Deployments (Lean single-stage footprint)
# ==============================================================================

FROM python:3.12-slim

# Install system dependencies, install python packages, and purge build tools in a single layer
# This avoids multi-stage copy duplication and layer bloat that causes "no space left on device"
WORKDIR /app

COPY requirements.txt .

RUN set -ex \
    && apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        curl \
    && pip install --no-cache-dir --default-timeout=1000 --retries 10 torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --default-timeout=1000 --retries 10 --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /root/.cache /tmp/* \
    && find /usr/local/lib/python3.12 -type d -name "__pycache__" -prune -exec rm -rf {} + \
    && find /usr/local/lib/python3.12 -type d -name "tests" -prune -exec rm -rf {} +

# Create dedicated non-root application user
RUN useradd -u 1000 -m -s /bin/bash appuser

# Application environment configuration
ENV PORT=8000 \
    HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1 \
    EXECUTION_TIMEOUT_MS=120000 \
    RATE_LIMIT_MAX=60 \
    RATE_LIMIT_WINDOW_S=60

# Copy application source code with correct ownership
COPY --chown=appuser:appuser invoice_parser /app/invoice_parser

# Switch to non-root user
USER appuser

# Expose default port
EXPOSE 8000

# Docker & Coolify healthcheck using dynamic PORT
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -f "http://localhost:${PORT:-8000}/health" || exit 1

# Start production FastAPI application with dynamic PORT resolution
CMD ["sh", "-c", "exec python -m uvicorn invoice_parser.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
