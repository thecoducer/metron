FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install production dependencies first (layer caching)
COPY pyproject.toml uv.lock* ./
RUN uv sync --group prod --no-dev --frozen

# Copy application code (secrets excluded via .dockerignore)
COPY . .

# Render injects PORT env var; default 8080 for local Docker testing
ENV PORT=8080

# Allow OAUTHLIB to work over HTTP behind Render's HTTPS proxy
ENV OAUTHLIB_INSECURE_TRANSPORT=0
ENV OAUTHLIB_RELAX_TOKEN_SCOPE=1

CMD exec uv run gunicorn wsgi:app -c gunicorn.conf.py
