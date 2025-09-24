FROM python:3.12-slim

# Prevent Python from buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1             PYTHONUNBUFFERED=1             PIP_NO_CACHE_DIR=1

# ffmpeg for yt-dlp merges/thumbnails
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates &&             rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ ./app/
WORKDIR /app

CMD ["python", "app/main.py"]
