"""Gunicorn configuration for production deployment.

Tuned for a 512 MB Render.com instance.  A single sync worker avoids
duplicating all in-memory caches and state managers.  The worker is
recycled after ``max_requests`` to reclaim any leaked memory.
"""

import os

# --- Server socket ---
bind = "0.0.0.0:" + os.environ.get("PORT", "8080")

# --- Worker processes ---
# Single worker: keeps one copy of all caches/state in 512 MB RAM.
workers = 1

# Default sync worker.
# worker_class defaults to "sync"

# --- Timeouts ---
keepalive = 65

# Worker silence timeout
timeout = 120

# Graceful shutdown window (seconds)
graceful_timeout = 30

# --- Memory management ---
# Recycle worker after N requests to reclaim any leaked memory.
max_requests = 1000
max_requests_jitter = 100

# --- Logging ---
accesslog = "-"  # stdout
errorlog = "-"  # stderr
loglevel = os.environ.get("LOG_LEVEL", "info")

# Don't log health-check noise
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sμs'

# --- Security ---
limit_request_line = 8190
limit_request_fields = 100

# --- Process naming ---
proc_name = "metron"


# --- Server hooks ---
def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Metron starting with %d worker(s)", workers)


def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

    # Eagerly initialise the Firestore client so the first HTTP request
    # doesn't pay the cost of importing firebase_admin, opening a gRPC
    # channel, and performing the TLS handshake (~1-2 s on cold start).
    try:
        from app.firebase_store import _db

        _db()
        server.log.info("Firestore client warmed up in worker %s", worker.pid)
    except Exception as exc:
        server.log.warning("Firestore warm-up failed: %s", exc)
