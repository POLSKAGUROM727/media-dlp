FROM python:3.12-slim

# Install system dependencies: ffmpeg for audio conversion + AtomicParsley for thumbnail embedding
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    atomicparsley \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates/ templates/

# Default download directory (mount your media share here)
ENV DOWNLOAD_DIR=/downloads
VOLUME ["/downloads"]

EXPOSE 5000

CMD ["python", "app.py"]
