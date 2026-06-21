#!/usr/bin/env bash
# Forward Stripe test webhooks to your local backend while you verify checkout.
# Prereqs: Stripe CLI, backend running on :8000
# Install (if cli.stripe.com is blocked): GitHub release -> ~/.local/bin/stripe
#   curl -fsSL -o /tmp/stripe.tar.gz "$(curl -fsSL https://api.github.com/repos/stripe/stripe-cli/releases/latest | python3 -c "import sys,json; print([a['browser_download_url'] for a in json.load(sys.stdin)['assets'] if 'linux_x86_64' in a['name']][0])")"
#   tar -xzf /tmp/stripe.tar.gz -C /tmp && mkdir -p ~/.local/bin && mv /tmp/stripe ~/.local/bin/
#
# Usage:
#   1. Put TEST keys + price IDs in backend/.env (see Phase 3 guide)
#   2. Terminal 1: cd backend && uvicorn app.main:app --reload --port 8000
#   3. Terminal 2: bash scripts/stripe-test-local.sh
#   4. Copy the whsec_... secret the CLI prints into backend/.env as STRIPE_WEBHOOK_SECRET
#   5. Restart backend, then test checkout from http://localhost:5173/app/billing
set -euo pipefail

echo "Forwarding Stripe test events -> http://localhost:8000/api/webhooks/stripe"
echo "Subscribe to checkout + subscription events..."
echo ""
echo "After the CLI prints a webhook signing secret (whsec_...), add it to backend/.env:"
echo "  STRIPE_WEBHOOK_SECRET=whsec_..."
echo "Then restart uvicorn and complete a test checkout."
echo ""

stripe listen \
  --forward-to localhost:8000/api/webhooks/stripe \
  --events checkout.session.completed,customer.subscription.created,customer.subscription.updated,customer.subscription.deleted,customer.subscription.trial_will_end,invoice.payment_failed,invoice.payment_succeeded
