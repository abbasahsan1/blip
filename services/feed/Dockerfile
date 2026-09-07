# ─── Stage 1: Build virtual environment ─────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN python -m venv /opt/venv
RUN /opt/venv/bin/pip install --no-cache-dir --upgrade pip

# Install shared core library first
COPY libs/common /libs/common
RUN /opt/venv/bin/pip install --no-cache-dir /libs/common

# Install service dependencies
COPY services/feed/requirements.txt .
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Re-point the symlink so /opt/venv/bin/python resolves correctly in distroless
RUN ln -sf /usr/bin/python3 /opt/venv/bin/python && \
    ln -sf /usr/bin/python3 /opt/venv/bin/python3

# ─── Stage 2: Distroless Runtime ───────────────────────────────────────────────
FROM gcr.io/distroless/python3-debian12

WORKDIR /app

ENV PATH="/opt/venv/bin:/usr/local/bin:/usr/bin:/bin" \
    PYTHONPATH="/app:/opt/venv/lib/python3.11/site-packages" \
    PYTHONUNBUFFERED=1

# Copy installed virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application code and tests
COPY services/feed/app/ ./app/
COPY services/feed/tests/ ./tests/

EXPOSE 8002

# Non-shell exec form entrypoint using direct binary execution
ENTRYPOINT ["/opt/venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
