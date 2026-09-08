# ─── Stage 1: Build virtual environment ─────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Ensure /usr/bin/python3 exists in builder so /opt/venv/bin/python resolves
RUN ln -sf /usr/local/bin/python3 /usr/bin/python3

# Copy pre-installed virtual environment from auth service
COPY --from=blipp-auth-service:latest /opt/venv /opt/venv

# Install shared core library
COPY libs/common /libs/common
RUN /opt/venv/bin/pip install --no-cache-dir --no-build-isolation --no-deps /libs/common

# In python:3.11-slim, /opt/venv/bin/python points to /usr/local/bin/python
# In gcr.io/distroless/python3-debian12, python3 binary is located at /usr/bin/python3
# Re-point the symlink so /opt/venv/bin/python resolves correctly in distroless
RUN ln -sf /usr/bin/python3 /opt/venv/bin/python && \
    ln -sf /usr/bin/python3 /opt/venv/bin/python3

# ─── Stage 2: Distroless Runtime ───────────────────────────────────────────────
FROM gcr.io/distroless/python3-debian12

WORKDIR /app

# Provide full explicit static PATH and wire PYTHONPATH directly into site-packages.
ENV PATH="/opt/venv/bin:/usr/local/bin:/usr/bin:/bin" \
    PYTHONPATH="/app:/opt/venv/lib/python3.11/site-packages" \
    PYTHONUNBUFFERED=1

# Copy installed virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY services/content_ingest/app/ ./app/

EXPOSE 8001

# Non-shell exec form entrypoint using direct binary execution
ENTRYPOINT ["/opt/venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
