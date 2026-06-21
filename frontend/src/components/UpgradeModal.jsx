import { Link } from 'react-router-dom'

export default function UpgradeModal({ open, message, onClose }) {
  if (!open) return null

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-card card">
        <div className="modal-card__icon">🔒</div>
        <h3>Upgrade to continue</h3>
        <p className="muted">{message || 'Your plan has expired. Subscribe to keep applying to jobs.'}</p>
        <div className="modal-card__actions">
          <Link to="/app/billing" className="btn-primary" onClick={onClose}>
            View plans
          </Link>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Not now
          </button>
        </div>
      </div>
    </div>
  )
}
