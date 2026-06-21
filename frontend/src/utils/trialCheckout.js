import { api } from '../api'

/**
 * After signup/login, send new users to Stripe trial checkout when billing is enabled
 * and they do not yet have a subscription.
 * @returns {boolean} true if redirecting to Stripe
 */
export async function redirectToTrialCheckoutIfNeeded() {
  try {
    const billing = await api.getBilling()
    if (
      !billing.stripe_configured
      || billing.has_stripe_subscription
      || billing.plan === 'unlimited'
      || billing.is_admin
    ) {
      return false
    }
    const { url } = await api.startTrialCheckout()
    if (url) {
      window.location.href = url
      return true
    }
  } catch {
    // Fall through — user can start trial manually from Billing.
  }
  return false
}
