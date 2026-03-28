#!/bin/bash
# Entrypoint script that starts Gunicorn + Cloudflare Tunnel together.
# If either process exits, the other is killed and the container stops.

set -euo pipefail

TUNNEL_NAME="${TUNNEL_NAME:-metron-tunnel}"
GUNICORN_PID=""
TUNNEL_PID=""

cleanup() {
    echo "[entrypoint] Shutting down..."

    if [ -n "$GUNICORN_PID" ] && kill -0 "$GUNICORN_PID" 2>/dev/null; then
        echo "[entrypoint] Stopping gunicorn (PID $GUNICORN_PID)..."
        kill -SIGTERM "$GUNICORN_PID" 2>/dev/null || true
        wait "$GUNICORN_PID" 2>/dev/null || true
    fi

    if [ -n "$TUNNEL_PID" ] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
        echo "[entrypoint] Stopping cloudflared (PID $TUNNEL_PID)..."
        kill -SIGTERM "$TUNNEL_PID" 2>/dev/null || true
        wait "$TUNNEL_PID" 2>/dev/null || true
    fi

    echo "[entrypoint] All processes stopped."
}

trap cleanup SIGTERM SIGINT EXIT

# --- Validate mounted secrets ---
missing=0
for f in config/flask-secret-key.txt config/firebase-credentials.json config/google-oauth-credentials.json; do
    if [ ! -f "$f" ]; then
        echo "[entrypoint] ERROR: required secret not found: $f"
        missing=1
    fi
done

if [ "$missing" -eq 1 ]; then
    echo "[entrypoint] Mount the secrets directory: -v /path/to/config:/app/config"
    exit 1
fi

CRED_DIR="${CLOUDFLARED_DIR:-/app/.cloudflared}"
if [ ! -d "$CRED_DIR" ]; then
    echo "[entrypoint] ERROR: cloudflared credentials not found at $CRED_DIR"
    echo "[entrypoint] Mount your tunnel credentials: -v ~/.cloudflared:/root/.cloudflared:ro"
    exit 1
fi

# Auto-detect the tunnel credentials JSON file
CREDS_FILE=$(find "$CRED_DIR" -maxdepth 1 -name '*.json' -print -quit)
if [ -z "$CREDS_FILE" ]; then
    echo "[entrypoint] ERROR: no tunnel credentials .json found in $CRED_DIR"
    exit 1
fi
echo "[entrypoint] Using tunnel credentials: $CREDS_FILE"

# --- Start gunicorn ---
echo "[entrypoint] Starting gunicorn on port ${PORT:-8000}..."
uv run gunicorn wsgi:app -c gunicorn.conf.py &
GUNICORN_PID=$!

sleep 2

if ! kill -0 "$GUNICORN_PID" 2>/dev/null; then
    echo "[entrypoint] ERROR: gunicorn failed to start."
    exit 1
fi

echo "[entrypoint] Gunicorn started (PID $GUNICORN_PID)."

# --- Start cloudflare tunnel ---
echo "[entrypoint] Starting cloudflare tunnel '${TUNNEL_NAME}'..."
cloudflared tunnel --credentials-file "$CREDS_FILE" run "$TUNNEL_NAME" &
TUNNEL_PID=$!

echo "[entrypoint] Cloudflare tunnel started (PID $TUNNEL_PID)."

# --- Wait for either process to exit ---
# bash wait -n returns when the first background job finishes.
wait -n "$GUNICORN_PID" "$TUNNEL_PID" 2>/dev/null
EXIT_CODE=$?

if ! kill -0 "$GUNICORN_PID" 2>/dev/null; then
    echo "[entrypoint] Gunicorn exited (code $EXIT_CODE). Tearing down tunnel..."
else
    echo "[entrypoint] Cloudflare tunnel exited (code $EXIT_CODE). Tearing down gunicorn..."
fi

# EXIT trap handles killing the surviving process
exit "$EXIT_CODE"
