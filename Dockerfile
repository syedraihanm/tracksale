# Multi-stage Dockerfile for Mobile Repair Shop Management System
FROM python:3.12-slim

# Install system dependencies & uv binary
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Kolkata \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Create non-root user and directories for SQLite database and backups
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data /app/backups && \
    chown -R appuser:appuser /app

# Copy dependency definition files
COPY pyproject.toml uv.lock* ./

# Install production dependencies via uv
RUN uv pip install --system -r pyproject.toml

# Copy application source code
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

VOLUME ["/app/data", "/app/backups"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
