#!/usr/bin/env bash
# Checklist before pasting .env.development into GitHub secret APP_ENV_DEV.
set -euo pipefail

ENV_FILE="${1:-.env.development}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy from .env.development.example"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

missing=()
warn=()

require() {
  local key=$1
  if [[ -z "${!key:-}" ]]; then
    missing+=("$key")
  fi
}

warn_if() {
  local key=$1
  local msg=$2
  if [[ -z "${!key:-}" ]]; then
    warn+=("$msg ($key)")
  fi
}

require JWT_SECRET
require ENCRYPTION_KEY
require DATABASE_URL
require GEMINI_API_KEY
require SMTP_USER
require SMTP_PASSWORD
require APP_BASE_URL
require CORS_ORIGINS

if [[ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]]; then
  warn+=("Remove CLOUDFLARE_TUNNEL_TOKEN from dev — use tunnel route to :8080 instead")
fi

warn_if STRIPE_WEBHOOK_SECRET "Stripe webhook (run scripts/stripe-setup-webhooks.sh test)"
warn_if STRIPE_SECRET_KEY "Stripe test secret key"
warn_if GOOGLE_CLIENT_SECRET "Google OAuth secret"
warn_if LINKEDIN_CLIENT_ID "LinkedIn OAuth (social login)"
warn_if LINKEDIN_CLIENT_SECRET "LinkedIn OAuth secret"

if [[ "${STRIPE_SECRET_KEY:-}" == sk_live_* ]]; then
  warn+=("STRIPE_SECRET_KEY looks LIVE — use sk_test_ on dev")
fi

echo "=== Dev env check: $ENV_FILE ==="
echo "LLM_PROVIDER=${LLM_PROVIDER:-gemini}"
echo "APP_BASE_URL=${APP_BASE_URL:-}"

if ((${#missing[@]})); then
  echo ""
  echo "MISSING (required):"
  printf '  - %s\n' "${missing[@]}"
  exit 1
fi

if ((${#warn[@]})); then
  echo ""
  echo "WARNINGS:"
  printf '  - %s\n' "${warn[@]}"
fi

echo ""
echo "OK — paste into GitHub secret APP_ENV_DEV"
