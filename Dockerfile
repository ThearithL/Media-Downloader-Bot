FROM python:3.12-slim

ARG WGCF_VERSION=2.3.1
ARG WIREPROXY_VERSION=1.1.3

# FFmpeg handles media conversion/merging. Deno handles modern YouTube JS
# challenges and the bgutil PO-token provider for public media.
# Tor provides a free userspace SOCKS5 egress. wgcf + wireproxy remain as
# a fallback Cloudflare WARP SOCKS5 egress without requiring /dev/net/tun.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl ca-certificates unzip git tar tor && \
    curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh && \
    deno --version && \
    ffmpeg -version | head -n 1 && \
    tor --version | head -n 1 && \
    curl -fsSL -o /usr/local/bin/wgcf "https://github.com/ViRb3/wgcf/releases/download/v${WGCF_VERSION}/wgcf_${WGCF_VERSION}_linux_amd64" && \
    echo "4fb7a136aa470ece11d17949c7db07b040ec9c604742dc8680bcf1889f85d0c8  /usr/local/bin/wgcf" | sha256sum -c - && \
    chmod +x /usr/local/bin/wgcf && \
    curl -fsSL -o /tmp/wireproxy.tar.gz "https://github.com/windtf/wireproxy/releases/download/v${WIREPROXY_VERSION}/wireproxy_linux_amd64.tar.gz" && \
    echo "e88c1d090740373fc606c1bafd81d9a5eadc642cce5667616e20e9d7a444f51c  /tmp/wireproxy.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/wireproxy.tar.gz -C /usr/local/bin wireproxy && \
    chmod +x /usr/local/bin/wireproxy && \
    rm -f /tmp/wireproxy.tar.gz && \
    git clone --depth 1 --branch 2.0.0 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil-ytdlp-pot-provider && \
    cd /opt/bgutil-ytdlp-pot-provider/server && \
    deno install --allow-scripts=npm:canvas --frozen && \
    apt-get purge -y --auto-remove unzip git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/start.sh

ENV PYTHONUNBUFFERED=1
ENV BGUTIL_SERVER_HOME=/opt/bgutil-ytdlp-pot-provider/server
ENV BGUTIL_BASE_URL=http://127.0.0.1:4416
ENV TOR_ENABLED=1
ENV WARP_ENABLED=1

CMD ["/app/start.sh"]
