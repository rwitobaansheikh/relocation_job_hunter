import { useEffect, useState } from 'react'
import { api } from '../api'
import HelpButton from '../components/HelpButton'

export default function Billing() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(null)
  const [message, setMessage] = useState(null)

  const load = async (sessionId, { afterCheckout = false } = {}) => {
    setLoading(true)
    try {
      const maxAttempts = afterCheckout ? 8 : 1
      let billing = null
      for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        billing = await api.getBilling(sessionId)
        const upgraded = billing?.has_stripe_subscription
          || ['basic', 'standard', 'pro'].includes(billing?.plan)
        if (!afterCheckout || upgraded || attempt === maxAttempts - 1) {
          break
        }
        await new Promise((resolve) => setTimeout(resolve, 1000))
      }
      setData(billing)
      return billing
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
      return null
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const sessionId = params.get('session_id')
    const status = params.get('status')

    const init = async () => {
      const billing = await load(sessionId, { afterCheckout: status === 'success' })
      if (status === 'success') {
        const upgraded = billing?.has_stripe_subscription
          || ['basic', 'standard', 'pro'].includes(billing?.plan)
        if (upgraded) {
          setMessage({ type: 'success', text: 'Subscription updated. Thank you!' })
          window.dispatchEvent(new CustomEvent('plan:updated'))
        } else {
          setMessage({
            type: 'info',
            text: 'Payment received — your plan is syncing. Refresh in a moment if it still shows Trial.',
          })
        }
        window.history.replaceState({}, '', window.location.pathname)
      } else if (status === 'cancel') {
        setMessage({ type: 'info', text: 'Checkout canceled.' })
        window.history.replaceState({}, '', window.location.pathname)
      }
    }

    init()
  }, [])

  const subscribe = async (tier) => {
    setBusy(tier)
    setMessage(null)
    try {
      const { url } = await api.checkout(tier)
      window.location.href = url
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
      setBusy(null)
    }
  }

  const startTrial = async () => {
    setBusy('trial')
    setMessage(null)
    try {
      const { url } = await api.startTrialCheckout()
      window.location.href = url
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
      setBusy(null)
    }
  }

  const manage = async () => {
    setBusy('portal')
    setMessage(null)
    try {
      const { url } = await api.openPortal()
      window.location.href = url
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
      setBusy(null)
    }
  }

  if (loading) return <p>Loading...</p>
  if (!data) return <p>Could not load billing information.</p>

  const planLabel = data.plan === 'unlimited' ? 'Unlimited (admin)' : data.plan
  const hasSubscription = ['basic', 'standard', 'pro'].includes(data.plan)
  const trialDays = data.trial_days || 3
  const showTrialCta =
    data.stripe_configured &&
    !data.has_stripe_subscription &&
    data.plan === 'trial' &&
    data.plan !== 'unlimited'

  return (
    <div>
      <h2 className="page-title">Plan & Billing</h2>
      <p className="page-subtitle">
        Start with a {trialDays}-day free trial on Basic, then upgrade as your job search scales.
      </p>

      {message && <div className={`alert alert-${message.type}`}>{message.text}</div>}

      {showTrialCta && (
        <div className="card trial-cta-card">
          <div>
            <h3 style={{ marginBottom: '0.35rem' }}>{trialDays}-day free trial</h3>
            <p className="muted" style={{ margin: 0 }}>
              Full Basic plan access for {trialDays} days. Add your card now — you will only be charged when the trial ends unless you cancel.
            </p>
          </div>
          <HelpButton
            className="btn-primary"
            onClick={startTrial}
            disabled={busy === 'trial'}
            title="Start free trial"
            help={`Unlock Basic plan features for ${trialDays} days. Stripe collects your payment method and charges automatically when the trial ends.`}
          >
            {busy === 'trial' ? 'Redirecting…' : `Start ${trialDays}-day free trial`}
          </HelpButton>
        </div>
      )}

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.6rem' }}>
          <div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Current plan</div>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, textTransform: 'capitalize' }}>{planLabel}</div>
            {data.plan === 'trial' && (
              <div className="muted">Free trial — {data.trial_days_left} day(s) left</div>
            )}
            {data.plan_status === 'trialing' && hasSubscription && (
              <div className="muted">Stripe trial active — billing starts when trial ends</div>
            )}
            {data.plan === 'expired' && (
              <div className="muted">Your trial has ended. Subscribe to keep applying.</div>
            )}
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className="muted">
              {data.usage.manual_today} / {data.limits.manual_per_day} manual applications today
            </div>
            <div className="muted">
              {data.usage.tailor_today} / {data.limits.tailor_per_day} document tailoring today
            </div>
            <div className="muted">
              {data.usage.llm_today} / {data.limits.llm_per_day} AI suggestions today
            </div>
            <div className="muted">
              {data.usage.loops_active} / {data.limits.max_loops} automation loops active
            </div>
          </div>
        </div>
        {hasSubscription && (
          <div style={{ marginTop: '1rem' }}>
            <HelpButton
              className="btn-secondary"
              onClick={manage}
              disabled={busy === 'portal'}
              title="Manage subscription"
              help="Opens the Stripe customer portal where you can update payment method, change plan, or cancel."
            >
              {busy === 'portal' ? 'Opening…' : 'Manage subscription'}
            </HelpButton>
          </div>
        )}
        {!data.stripe_configured && (
          <p className="muted" style={{ marginTop: '0.8rem' }}>
            Payments are not configured on this server yet.
          </p>
        )}
      </div>

      <div className="pricing-grid">
        {data.tiers.map((t) => {
          const isCurrent = data.plan === t.id
          return (
            <div key={t.id} className={`card pricing-card${isCurrent ? ' pricing-current' : ''}`}>
              <h3 style={{ marginBottom: '0.2rem' }}>{t.name}</h3>
              <div className="pricing-price">
                {t.price_display}
              </div>
              {t.is_estimate && (
                <div className="muted" style={{ fontSize: '0.78rem' }}>
                  ≈ estimated in {t.currency}; charged in your local currency at checkout
                </div>
              )}
              <ul className="pricing-features">
                {t.features.map((f, i) => <li key={i}>{f}</li>)}
              </ul>
              <HelpButton
                className={isCurrent ? 'btn-secondary' : 'btn-primary'}
                style={{ width: '100%' }}
                disabled={busy === t.id || isCurrent || !data.stripe_configured}
                onClick={() => subscribe(t.id)}
                title={isCurrent ? 'Current plan' : `Choose ${t.name}`}
                help={isCurrent
                  ? 'You are already on this plan.'
                  : `Subscribe to ${t.name} — unlock more daily applications and automation loops. You'll be redirected to secure checkout.`}
              >
                {isCurrent ? 'Current plan' : busy === t.id ? 'Redirecting…' : `Choose ${t.name}`}
              </HelpButton>
            </div>
          )
        })}
      </div>
    </div>
  )
}
