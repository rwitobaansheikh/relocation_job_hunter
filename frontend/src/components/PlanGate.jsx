import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import UpgradeModal from './UpgradeModal'

const ALLOWED_PATHS = ['/app/billing', '/app/settings', '/app/feedback']

export default function PlanGate({ children }) {
  const location = useLocation()
  const [billing, setBilling] = useState(null)
  const [upgradeOpen, setUpgradeOpen] = useState(false)
  const [upgradeMessage, setUpgradeMessage] = useState('')

  const refreshBilling = () => {
    api.getBilling().then(setBilling).catch(() => {})
  }

  useEffect(() => {
    refreshBilling()
    const onPlanUpdated = () => refreshBilling()
    window.addEventListener('plan:updated', onPlanUpdated)
    return () => window.removeEventListener('plan:updated', onPlanUpdated)
  }, [location.pathname])

  useEffect(() => {
    const onUpgrade = (event) => {
      setUpgradeMessage(event.detail?.message || '')
      setUpgradeOpen(true)
      refreshBilling()
    }
    window.addEventListener('plan:upgrade_required', onUpgrade)
    return () => window.removeEventListener('plan:upgrade_required', onUpgrade)
  }, [])

  const isExpired = billing?.plan === 'expired'
  const onRestrictedPage = !ALLOWED_PATHS.some((p) => location.pathname.startsWith(p))

  useEffect(() => {
    if (isExpired && onRestrictedPage) {
      setUpgradeMessage('Your free trial has ended. Choose a plan to unlock job search, document tailoring, and application tracking.')
      setUpgradeOpen(true)
    }
  }, [isExpired, onRestrictedPage])

  return (
    <>
      {isExpired && onRestrictedPage && (
        <div className="plan-banner plan-banner--expired">
          <span>Your trial has ended — subscribe to continue applying.</span>
          <a href="/app/billing" className="btn-primary btn-sm">Upgrade now</a>
        </div>
      )}
      {billing?.plan === 'trial' && billing.trial_days_left <= 1 && (
        <div className="plan-banner plan-banner--warning">
          <span>
            {billing.trial_days_left <= 0
              ? 'Your trial ends today.'
              : `${billing.trial_days_left} day(s) left in your free trial.`}
          </span>
          <a href="/app/billing" className="btn-secondary btn-sm">Manage plan</a>
        </div>
      )}
      {children}
      <UpgradeModal
        open={upgradeOpen}
        message={upgradeMessage}
        onClose={() => setUpgradeOpen(false)}
      />
    </>
  )
}
