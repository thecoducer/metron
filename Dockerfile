FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# curl needed for container healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install production dependencies first (layer caching)
COPY pyproject.toml uv.lock* ./
RUN uv sync --group prod --no-dev --frozen

# Copy application code (secrets excluded via .dockerignore)
COPY . .

ENV PORT=8000
ENV OAUTHLIB_INSECURE_TRANSPORT=0
ENV OAUTHLIB_RELAX_TOKEN_SCOPE=1

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fs http://localhost:${PORT}/health || exit 1

EXPOSE ${PORT}

CMD ["uv", "run", "gunicorn", "wsgi:app", "-c", "gunicorn.conf.py"]
