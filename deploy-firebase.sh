#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Metron — Deploy Firebase Hosting (metron.web.app)
#
# Firebase Hosting acts as a reverse proxy to the Cloud Run
# backend. All requests are forwarded to the Cloud Run service
# "metron" in asia-south1.
#
# Prerequisites:
#   1. Firebase CLI installed (npm i -g firebase-tools)
#   2. Authenticated: firebase login
#   3. Cloud Run service "metron" already deployed (./deploy.sh)
#   4. Firebase Hosting site "metron" created in the project
#      (firebase hosting:sites:create metron --project extreme-outpost-480113-c6)
#
# Usage:
#   ./deploy-firebase.sh              # deploy with defaults
#   ./deploy-firebase.sh --project X  # override project
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────
PROJECT="${FIREBASE_PROJECT:-extreme-outpost-480113-c6}"
SITE="metron"

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
        *) err "Unknown argument: $1" ;;
    esac
done

# ─── Preflight checks ───────────────────────────────────────
command -v firebase &>/dev/null || err "Firebase CLI not installed. Run: npm i -g firebase-tools"
[[ -f firebase.json ]] || err "firebase.json not found. Run from project root."
[[ -d firebase-public ]] || err "firebase-public/ directory not found."

info "Deploying Firebase Hosting for site '${SITE}' in project '${PROJECT}'"

# ─── Ensure the hosting site exists ─────────────────────────
info "Checking if hosting site '${SITE}' exists..."
if ! firebase hosting:sites:list --project="$PROJECT" 2>/dev/null | grep -q "$SITE"; then
    warn "Hosting site '${SITE}' not found. Creating..."
    firebase hosting:sites:create "$SITE" --project="$PROJECT" || err "Failed to create hosting site '${SITE}'"
    ok "Hosting site '${SITE}' created"
fi

# ─── Apply deploy target ────────────────────────────────────
info "Setting deploy target..."
firebase target:apply hosting "$SITE" "$SITE" --project="$PROJECT" 2>/dev/null || true

# ─── Deploy ──────────────────────────────────────────────────
info "Deploying to Firebase Hosting..."
firebase deploy --only hosting:"$SITE" --project="$PROJECT"

ok "Deployed successfully!"
echo ""
echo -e "  ${GREEN}Live at:${NC} https://${SITE}.web.app"
echo -e "  ${GREEN}Alt URL:${NC} https://${SITE}.firebaseapp.com"
echo ""

# ─── Post-deploy reminders ──────────────────────────────────
echo -e "${YELLOW}── Post-deploy checklist ──${NC}"
echo "  1. Add https://${SITE}.web.app/auth/google/callback to Google OAuth"
echo "     authorized redirect URIs (Google Cloud Console > APIs & Services > Credentials)"
echo "  2. Add https://${SITE}.web.app/callback to Zerodha KiteConnect redirect URL"
echo "  3. Verify SSE works: open https://${SITE}.web.app and check real-time updates"
