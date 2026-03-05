#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Metron — Deploy to Google Cloud Run (asia-south1)
#
# Prerequisites:
#   1. gcloud CLI installed and authenticated
#   2. A GCP project with Cloud Run, Firestore, and
#      Secret Manager APIs enabled
#   3. Secrets created in Secret Manager (see below)
#
# Required secrets in Secret Manager:
#   flask-secret-key            — random hex string (python3 -c "import secrets; print(secrets.token_hex(32))")
#   zerodha-token-secret        — random string for encrypting Zerodha tokens
#   firebase-credentials        — full JSON of Firebase service account key
#   google-oauth-credentials    — full JSON of Google OAuth client secrets
#
# Usage:
#   ./deploy.sh                     # deploy with defaults
#   ./deploy.sh --project my-proj   # override project
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────
SERVICE_NAME="metron"
REGION="asia-south1"
PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
MAX_INSTANCES="${MAX_INSTANCES:-1}"
MEMORY="${MEMORY:-512Mi}"
CPU="${CPU:-1}"
TIMEOUT="${TIMEOUT:-1800}"          # 30 min — matches SSE_MAX_CONNECTION_AGE
CONCURRENCY="${CONCURRENCY:-80}"    # max concurrent requests per instance

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ─── Parse args ──────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --project) PROJECT="$2"; shift 2 ;;
        --region)  REGION="$2"; shift 2 ;;
        --service) SERVICE_NAME="$2"; shift 2 ;;
        *) err "Unknown argument: $1" ;;
    esac
done

[[ -z "$PROJECT" ]] && err "No GCP project set. Use --project or gcloud config set project."

info "Deploying ${SERVICE_NAME} to ${REGION} in project ${PROJECT}"

# ─── Verify secrets exist ────────────────────────────────────
info "Checking Secret Manager secrets..."
REQUIRED_SECRETS=(flask-secret-key zerodha-token-secret firebase-credentials google-oauth-credentials)
for secret in "${REQUIRED_SECRETS[@]}"; do
    if ! gcloud secrets describe "$secret" --project="$PROJECT" &>/dev/null; then
        err "Secret '${secret}' not found in Secret Manager. Create it first:\n  gcloud secrets create ${secret} --project=${PROJECT}\n  echo -n 'value' | gcloud secrets versions add ${secret} --data-file=- --project=${PROJECT}"
    fi
done
ok "All secrets found"

# ─── Resolve Cloud Run URL for SSE direct access ────────────
# If CLOUD_RUN_URL is already set (e.g. re-deploy), use it.
# Otherwise, try to fetch it from the existing service.
if [[ -z "${CLOUD_RUN_URL:-}" ]]; then
    CLOUD_RUN_URL=$(gcloud run services describe "$SERVICE_NAME" \
        --project="$PROJECT" --region="$REGION" \
        --format='value(status.url)' 2>/dev/null || echo "")
fi

# ─── Deploy ──────────────────────────────────────────────────
info "Building and deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
    --project="$PROJECT" \
    --region="$REGION" \
    --source=. \
    --platform=managed \
    --allow-unauthenticated \
    --memory="$MEMORY" \
    --cpu="$CPU" \
    --min-instances="$MIN_INSTANCES" \
    --max-instances="$MAX_INSTANCES" \
    --timeout="${TIMEOUT}s" \
    --concurrency="$CONCURRENCY" \
    --set-env-vars="FLASK_ENV=production,CLOUD_RUN_URL=${CLOUD_RUN_URL}" \
    --set-secrets="\
FLASK_SECRET_KEY=flask-secret-key:latest,\
ZERODHA_TOKEN_SECRET=zerodha-token-secret:latest,\
FIREBASE_CREDENTIALS=firebase-credentials:latest,\
GOOGLE_OAUTH_CREDENTIALS=google-oauth-credentials:latest" \
    --port=8080

# ─── Output ──────────────────────────────────────────────────
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --project="$PROJECT" --region="$REGION" \
    --format='value(status.url)' 2>/dev/null)

echo ""
ok "Deployed successfully!"
echo ""
info "Service URL: ${SERVICE_URL}"
echo ""
warn "IMPORTANT: Add these URLs to your Google OAuth Authorized redirect URIs:"
echo "  ${SERVICE_URL}/auth/google/callback"
echo ""
warn "And to your Zerodha KiteConnect redirect URL:"
echo "  ${SERVICE_URL}/callback"
