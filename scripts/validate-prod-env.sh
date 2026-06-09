#!/usr/bin/env bash
# Quick checklist before pasting .env.production into GitHub APP_ENV secret.
set -euo pipefail

ENV_FILE="${1:-.env.production}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  exit 1
fi

# shellcheck disable=SC1090
set -a
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

warn_if_empty() {
  local key=$1
  local label=$2
  if [[ -z "${!key:-}" ]]; then
    warn+=("$label ($key)")
  fi
}

# Required for any deploy
require JWT_SECRET
require ENCRYPTION_KEY
require DATABASE_URL
require OLLAMA_BASE_URL
require OLLAMA_MODEL
require HUNTER_API_KEY
require SMTP_USER
require SMTP_PASSWORD
require APP_BASE_URL
require CORS_ORIGINS

# Phases 3–4 (warn only)
warn_if_empty STRIPE_SECRET_KEY "Stripe (Phase 3)"
warn_if_empty STRIPE_WEBHOOK_SECRET "Stripe webhook (Phase 3, after domain live)"
warn_if_empty CLOUDFLARE_TUNNEL_TOKEN "Cloudflare tunnel (Phase 4)"

echo "=== Production env check: $ENV_FILE ==="
echo "LLM_PROVIDER=${LLM_PROVIDER:-ollama}"
echo "OLLAMA_MODEL=${OLLAMA_MODEL:-}"
echo "APP_BASE_URL=${APP_BASE_URL:-}"

if ((${#missing[@]})); then
  echo ""
  echo "MISSING (required):"
  printf '  - %s\n' "${missing[@]}"
  exit 1
fi

if ((${#warn[@]})); then
  echo ""
  echo "TODO before go-live:"
  printf '  - %s\n' "${warn[@]}"
fi

echo ""
echo "OK — ready to paste into GitHub secret APP_ENV (excluding this script output)."
