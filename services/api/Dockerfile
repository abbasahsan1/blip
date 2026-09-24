# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# Blipps v1 — Single-stage Dockerfile
#
# Why single-stage (not multi-stage):
#   boto3, asyncpg, bcrypt, mutagen are all compiled/binary wheels that
#   pip pulls as pre-built manylinux wheels on slim. A builder stage would
#   save nothing here — pip doesn't compile from source for any of these
#   on linux/amd64. Keep it simple and debuggable (v1 principle).
#
# Later improvement: switch to distroless/cc or chainguard python base
#   once the app is stable and you want a smaller attack surface.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim

# ── System dependencies ───────────────────────────────────────────────────
# libpq-dev: not needed (asyncpg is pure-C wheel, no libpq)
# We only need ca-certificates for outbound TLS (Neon, B2, Redis)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user ─────────────────────────────────────────────────────────
RUN groupadd --gid 1001 blipps \
    && useradd --uid 1001 --gid blipps --no-create-home blipps

# ── Working directory ─────────────────────────────────────────────────────
WORKDIR /app

# ── Dependency layer (cached unless requirements.txt changes) ─────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────
COPY main.py database.py models.py deps.py routes.py storage.py ./

# ── Ownership ─────────────────────────────────────────────────────────────
RUN chown -R blipps:blipps /app

# ── Runtime user ─────────────────────────────────────────────────────────
USER blipps

# ── Port ──────────────────────────────────────────────────────────────────
# Render injects $PORT at runtime. We use shell-form CMD so the variable
# is expanded by /bin/sh before exec. Default to 8000 locally.
EXPOSE 8000

# ── Entrypoint ────────────────────────────────────────────────────────────
# shell form (not exec form) intentionally — lets $PORT expand at runtime
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --log-level info
