FROM python:3.12-slim

WORKDIR /app

# Install production dependencies first (layer caching)
COPY requirements.txt requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt

# Copy application code (secrets excluded via .dockerignore)
COPY . .

# Render injects PORT env var; default 8080 for local Docker testing
ENV PORT=8080

# Allow OAUTHLIB to work over HTTP behind Render's HTTPS proxy
ENV OAUTHLIB_INSECURE_TRANSPORT=0
ENV OAUTHLIB_RELAX_TOKEN_SCOPE=1

CMD exec gunicorn wsgi:app -c gunicorn.conf.py
