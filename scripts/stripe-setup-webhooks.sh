#!/usr/bin/env bash
# Register or update Stripe webhook endpoints for trial checkout + auto-charge.
#
# Usage:
#   bash scripts/stripe-setup-webhooks.sh test   # dev.jobapplicationflow.com (test keys)
#   bash scripts/stripe-setup-webhooks.sh live   # jobapplicationflow.com (live keys)
set -euo pipefail

MODE="${1:-test}"
EVENTS=(
  checkout.session.completed
  customer.subscription.created
  customer.subscription.updated
  customer.subscription.deleted
  customer.subscription.trial_will_end
  invoice.payment_failed
  invoice.payment_succeeded
)

if [[ "$MODE" == "live" ]]; then
  URL="https://jobapplicationflow.com/api/webhooks/stripe"
  LIVE_FLAG=(--live)
  echo "=== Live (production) webhook: $URL ==="
else
  URL="https://dev.jobapplicationflow.com/api/webhooks/stripe"
  LIVE_FLAG=()
  echo "=== Test (dev) webhook: $URL ==="
fi

event_args=()
for ev in "${EVENTS[@]}"; do
  event_args+=(--enabled-events "$ev")
done

existing_id=""
mapfile -t endpoints < <(stripe webhook_endpoints list "${LIVE_FLAG[@]}" --limit 20 -q "data[].id" 2>/dev/null || true)
for id in "${endpoints[@]}"; do
  ep_url=$(stripe webhook_endpoints retrieve "$id" "${LIVE_FLAG[@]}" -q url 2>/dev/null || true)
  if [[ "$ep_url" == "$URL" ]]; then
    existing_id="$id"
    break
  fi
done

if [[ -n "$existing_id" ]]; then
  echo "Updating existing endpoint $existing_id ..."
  stripe webhook_endpoints update "$existing_id" "${LIVE_FLAG[@]}" \
    --url "$URL" \
    "${event_args[@]}" \
    --description "Job Application Flow ($MODE) — trial + subscriptions"
else
  echo "Creating webhook endpoint ..."
  stripe webhook_endpoints create "${LIVE_FLAG[@]}" \
    --url "$URL" \
    "${event_args[@]}" \
    --description "Job Application Flow ($MODE) — trial + subscriptions"
fi

echo ""
echo "Done. Copy the signing secret (whsec_...) into your env:"
if [[ "$MODE" == "live" ]]; then
  echo "  .env.production     -> STRIPE_WEBHOOK_SECRET"
  echo "  GitHub secret APP_ENV (re-deploy production)"
else
  echo "  .env.development    -> STRIPE_WEBHOOK_SECRET"
  echo "  GitHub secret APP_ENV_DEV (re-deploy dev branch)"
fi
echo ""
stripe webhook_endpoints list "${LIVE_FLAG[@]}" --limit 5
