"""Gunicorn configuration for production deployment.

Optimised for request/response workloads (no SSE / long-lived connections).
"""

import os

# --- Server socket ---
bind = "0.0.0.0:" + os.environ.get("PORT", "8080")

# --- Worker processes ---
workers = int(os.environ.get("WEB_CONCURRENCY", 1))

# Default sync worker — no gevent needed without SSE.
# worker_class defaults to "sync"

# --- Timeouts ---
keepalive = 65

# Worker silence timeout
timeout = 120

# Graceful shutdown window (seconds)
graceful_timeout = 30

# --- Logging ---
accesslog = "-"       # stdout
errorlog = "-"        # stderr
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
