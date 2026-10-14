#!/bin/sh
set -u

log() {
  printf '%s\n' "[startup] $*"
}

BGUTIL_PID=""
WARP_PID=""
TOR_PID=""

cleanup() {
  [ -n "$TOR_PID" ] && kill "$TOR_PID" 2>/dev/null || true
  [ -n "$WARP_PID" ] && kill "$WARP_PID" 2>/dev/null || true
  [ -n "$BGUTIL_PID" ] && kill "$BGUTIL_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

start_bgutil() {
  log "Starting bgutil PO-token provider on 127.0.0.1:4416"
  (
    cd "${BGUTIL_SERVER_HOME:-/opt/bgutil-ytdlp-pot-provider/server}" || exit 1
    exec deno run --allow-env --allow-net --allow-ffi=. --allow-read=. src/main.ts --host 127.0.0.1 --port 4416
  ) &
  BGUTIL_PID=$!
}

setup_tor_proxy() {
  if [ "${TOR_ENABLED:-1}" != "1" ]; then
    log "Tor disabled by TOR_ENABLED"
    return 1
  fi

  if ! command -v tor >/dev/null 2>&1; then
    log "Tor binary is unavailable"
    return 1
  fi

  workdir=/tmp/tor-data
  rm -rf "$workdir"
  mkdir -p "$workdir"
  chown debian-tor:debian-tor "$workdir" 2>/dev/null || true

  log "Starting Tor SOCKS5 proxy on 127.0.0.1:9050"
  tor -f /dev/null \
    --User debian-tor \
    --RunAsDaemon 0 \
    --SocksPort 127.0.0.1:9050 \
    --DataDirectory "$workdir" \
    --Log "notice file /tmp/tor.log" >/tmp/tor-stdout.log 2>&1 &
  TOR_PID=$!

  attempt=1
  while [ "$attempt" -le 30 ]; do
    if curl -fsS --max-time 10 --proxy socks5h://127.0.0.1:9050 \
      https://www.cloudflare.com/cdn-cgi/trace 2>/dev/null | grep -q '^ip='; then
      export YTDLP_PROXY_URL="socks5://127.0.0.1:9050"
      log "Tor proxy is ready; YouTube will use Tor egress"
      return 0
    fi
    if ! kill -0 "$TOR_PID" 2>/dev/null; then
      log "Tor exited before SOCKS5 became ready"
      [ -s /tmp/tor.log ] && tail -n 5 /tmp/tor.log || true
      return 1
    fi
    attempt=$((attempt + 1))
    sleep 2
  done

  log "Tor did not become ready; falling back to WARP/direct egress"
  kill "$TOR_PID" 2>/dev/null || true
  TOR_PID=""
  unset YTDLP_PROXY_URL 2>/dev/null || true
  return 1
}

setup_warp_proxy() {
  if [ "${WARP_ENABLED:-1}" != "1" ]; then
    log "WARP disabled by WARP_ENABLED"
    return 1
  fi

  workdir=/tmp/warp
  rm -rf "$workdir"
  mkdir -p "$workdir"
  cd "$workdir" || return 1

  log "Registering Cloudflare WARP account"
  registered=0
  attempt=1
  while [ "$attempt" -le 3 ]; do
    if wgcf register --accept-tos >/tmp/wgcf-register.log 2>&1; then
      registered=1
      break
    fi
    log "WARP registration attempt $attempt failed"
    attempt=$((attempt + 1))
    sleep 3
  done

  if [ "$registered" -ne 1 ] || [ ! -s wgcf-account.toml ]; then
    log "WARP registration unavailable; continuing without WARP"
    return 1
  fi

  if ! wgcf generate --keepalive >/tmp/wgcf-generate.log 2>&1; then
    log "WARP profile generation failed; continuing without WARP"
    return 1
  fi

  cp wgcf-profile.conf wireproxy.conf
  cat >> wireproxy.conf <<'CFG'

[Socks5]
BindAddress = 127.0.0.1:25344
CFG

  log "Starting WARP userspace SOCKS5 proxy on 127.0.0.1:25344"
  wireproxy -c "$workdir/wireproxy.conf" >/tmp/wireproxy.log 2>&1 &
  WARP_PID=$!

  attempt=1
  while [ "$attempt" -le 12 ]; do
    trace="$(curl -fsS --max-time 8 --proxy socks5h://127.0.0.1:25344 https://www.cloudflare.com/cdn-cgi/trace 2>/dev/null || true)"
    if printf '%s\n' "$trace" | grep -q '^warp=on$'; then
      export YTDLP_PROXY_URL="socks5://127.0.0.1:25344"
      log "Cloudflare WARP is ON; YouTube will use the WARP proxy"
      return 0
    fi
    if ! kill -0 "$WARP_PID" 2>/dev/null; then
      log "wireproxy exited before WARP became ready"
      return 1
    fi
    attempt=$((attempt + 1))
    sleep 2
  done

  log "WARP did not become ready; continuing without WARP"
  kill "$WARP_PID" 2>/dev/null || true
  WARP_PID=""
  unset YTDLP_PROXY_URL 2>/dev/null || true
  return 1
}

start_bgutil
if ! setup_tor_proxy; then
  setup_warp_proxy || true
fi

cd /app || exit 1
log "Starting Media Downloader Bot"
trap - INT TERM EXIT
exec gunicorn app:app --bind "0.0.0.0:${PORT:-10000}" --workers 1 --threads 4 --timeout 180
