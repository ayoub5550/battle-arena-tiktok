FROM python:3.11-slim

# System deps: FFmpeg + fonts
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg curl fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY *.py ./
COPY cookies.json ./
COPY music/ ./music/

CMD ["python", "-u", "main.py"]
