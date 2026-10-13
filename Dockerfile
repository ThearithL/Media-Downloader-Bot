FROM python:3.12-slim

# FFmpeg handles media conversion/merging. Deno handles modern YouTube JS
# challenges and the bgutil PO-token provider script for public media.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl ca-certificates unzip git && \
    curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh && \
    deno --version && \
    ffmpeg -version | head -n 1 && \
    git clone --depth 1 --branch 2.0.0 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil-ytdlp-pot-provider && \
    cd /opt/bgutil-ytdlp-pot-provider/server && \
    deno install --allow-scripts=npm:canvas --frozen && \
    apt-get purge -y --auto-remove curl unzip git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV BGUTIL_SERVER_HOME=/opt/bgutil-ytdlp-pot-provider/server

CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 180"]
