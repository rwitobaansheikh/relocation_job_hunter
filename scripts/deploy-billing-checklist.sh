#!/usr/bin/env bash
# Reminder: after editing .env.production, paste the full file into GitHub secret APP_ENV
# and re-deploy main. For dev: APP_ENV_DEV + push to dev branch.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${1:-$ROOT/.env.production}"

bash "$ROOT/scripts/validate-prod-env.sh" "$ENV_FILE"

echo ""
echo "Next steps to activate trial billing in production:"
echo "  1. Register Stripe webhooks:"
echo "       bash scripts/stripe-setup-webhooks.sh live"
echo "       bash scripts/stripe-setup-webhooks.sh test   # for dev"
echo "  2. Copy whsec_... into STRIPE_WEBHOOK_SECRET in this env file"
echo "  3. Paste entire $ENV_FILE into GitHub → Settings → Secrets → APP_ENV"
echo "  4. Push to main (or run Build & Deploy workflow) to reload the instance"
echo ""
echo "SMTP is used for trial-ending and trial-expired emails (already in this env)."
