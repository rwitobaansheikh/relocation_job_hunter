import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Billing() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(null)
  const [message, setMessage] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      setData(await api.getBilling())
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
    setLoading(false)
  }

  useEffect(() => {
    load()
    const params = new URLSearchParams(window.location.search)
    const status = params.get('status')
    if (status === 'success') setMessage({ type: 'success', text: 'Subscription updated. Thank you!' })
    else if (status === 'cancel') setMessage({ type: 'info', text: 'Checkout canceled.' })
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

  return (
    <div>
      <h2 className="page-title">Plan & Billing</h2>
      <p className="page-subtitle">Choose a plan to unlock more automation loops and daily applications.</p>

      {message && <div className={`alert alert-${message.type}`}>{message.text}</div>}

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.6rem' }}>
          <div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Current plan</div>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, textTransform: 'capitalize' }}>{planLabel}</div>
            {data.plan === 'trial' && (
              <div className="muted">Free trial — {data.trial_days_left} day(s) left</div>
            )}
            {data.plan === 'expired' && (
              <div className="muted">Your trial has ended. Subscribe to keep applying.</div>
            )}
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className="muted">
              {data.usage.manual_today} / {data.limits.manual_per_day} manual applications used today
            </div>
            <div className="muted">
              {data.usage.loops_active} / {data.limits.max_loops} automation loops active
            </div>
          </div>
        </div>
        {hasSubscription && (
          <div style={{ marginTop: '1rem' }}>
            <button className="btn-secondary" onClick={manage} disabled={busy === 'portal'}>
              {busy === 'portal' ? 'Opening…' : 'Manage subscription'}
            </button>
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
              <button
                className={isCurrent ? 'btn-secondary' : 'btn-primary'}
                style={{ width: '100%' }}
                disabled={busy === t.id || isCurrent || !data.stripe_configured}
                onClick={() => subscribe(t.id)}
              >
                {isCurrent ? 'Current plan' : busy === t.id ? 'Redirecting…' : `Choose ${t.name}`}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
