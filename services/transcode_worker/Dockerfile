FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app:/opt/venv/lib/python3.11/site-packages"

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        procps && \
    rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
RUN pip install --no-cache-dir --upgrade pip

# Install shared core library first
COPY libs/common /libs/common
RUN pip install --no-cache-dir /libs/common

# Install service dependencies
COPY services/transcode_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/transcode_worker/app/ ./app/

ENTRYPOINT ["python", "-m", "app.main"]
