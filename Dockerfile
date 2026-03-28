FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install cloudflared for Cloudflare Tunnel
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    ARCH=$(dpkg --print-architecture) && \
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}" \
        -o /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared && \
    apt-get purge -y curl && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install production dependencies first (layer caching)
COPY pyproject.toml uv.lock* ./
RUN uv sync --group prod --no-dev --frozen

# Copy application code (secrets excluded via .dockerignore)
COPY . .

# Gunicorn listens on this port; must match cloudflared tunnel config
ENV PORT=8000

ENV OAUTHLIB_INSECURE_TRANSPORT=0
ENV OAUTHLIB_RELAX_TOKEN_SCOPE=1

# Tunnel name (override with -e TUNNEL_NAME=your-tunnel)
ENV TUNNEL_NAME=metron-tunnel

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
