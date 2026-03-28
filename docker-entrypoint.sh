#!/bin/bash
# Tunnel sidecar entrypoint.
# Waits for the app to be healthy, runs cloudflared, and exits if the app dies.

set -euo pipefail

APP_URL="${APP_URL:-http://app:8000}"
HEALTHCHECK_INTERVAL="${HEALTHCHECK_INTERVAL:-5}"
TUNNEL_NAME="${TUNNEL_NAME:-metron-tunnel}"
CRED_DIR="${CLOUDFLARED_CRED_DIR:-/cloudflared}"
TUNNEL_CONFIG="${TUNNEL_CONFIG:-}"
TUNNEL_PID=""

cleanup() {
    echo "[tunnel] Shutting down..."
    if [ -n "$TUNNEL_PID" ] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
        kill -SIGTERM "$TUNNEL_PID" 2>/dev/null || true
        wait "$TUNNEL_PID" 2>/dev/null || true
    fi
    echo "[tunnel] Stopped."
}

trap cleanup SIGTERM SIGINT EXIT

# --- Wait for app to be reachable ---
echo "[tunnel] Waiting for app at ${APP_URL}/health ..."
retries=0
max_retries=60
until curl -fs "${APP_URL}/health" > /dev/null 2>&1; do
    retries=$((retries + 1))
    if [ "$retries" -ge "$max_retries" ]; then
        echo "[tunnel] ERROR: app not reachable after ${max_retries} attempts. Exiting."
        exit 1
    fi
    sleep 2
done
echo "[tunnel] App is healthy."

# --- Auto-detect credentials file ---
CREDS_FILE=$(find "$CRED_DIR" -maxdepth 1 -name '*.json' -print -quit)
if [ -z "$CREDS_FILE" ]; then
    echo "[tunnel] ERROR: no tunnel credentials .json found in $CRED_DIR"
    exit 1
fi
echo "[tunnel] Using credentials: $CREDS_FILE"

# --- Start cloudflared ---
echo "[tunnel] Starting cloudflare tunnel '${TUNNEL_NAME}'..."
TUNNEL_ARGS=(tunnel --credentials-file "$CREDS_FILE")
if [ -n "$TUNNEL_CONFIG" ]; then
    TUNNEL_ARGS+=(--config "$TUNNEL_CONFIG")
    echo "[tunnel] Using config: $TUNNEL_CONFIG"
fi
TUNNEL_ARGS+=(run "$TUNNEL_NAME")
cloudflared "${TUNNEL_ARGS[@]}" &
TUNNEL_PID=$!

# --- Monitor app health; exit if app goes down ---
while kill -0 "$TUNNEL_PID" 2>/dev/null; do
    if ! curl -fs "${APP_URL}/health" > /dev/null 2>&1; then
        echo "[tunnel] App health check failed. Stopping tunnel..."
        exit 1
    fi
    sleep "$HEALTHCHECK_INTERVAL"
done

# cloudflared exited on its own
wait "$TUNNEL_PID" 2>/dev/null
EXIT_CODE=$?
echo "[tunnel] cloudflared exited with code $EXIT_CODE"
exit "$EXIT_CODE"
