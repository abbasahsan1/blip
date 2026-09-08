# ─── Stage 1: Build virtual environment ─────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN python -m venv /opt/venv
RUN /opt/venv/bin/pip install --no-cache-dir --upgrade pip

# Install service dependencies
COPY services/social_graph/requirements.txt .
RUN sed -i '/libs\/common/d' requirements.txt && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Install shared core library directly into site-packages
COPY libs/common /libs/common
RUN /opt/venv/bin/pip install --no-cache-dir --no-deps /libs/common && \
    cp -r /libs/common/blipp_common /opt/venv/lib/python3.11/site-packages/

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

# Copy application code
COPY services/social_graph/app/ ./app/

EXPOSE 8003

# Non-shell exec form entrypoint using direct binary execution
ENTRYPOINT ["/opt/venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
