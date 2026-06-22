export default function DidYouApplyModal({ open, jobTitle, company, onYes, onNo }) {
  if (!open) return null

  const label = [jobTitle, company].filter(Boolean).join(' at ')

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="did-you-apply-title">
      <div className="modal-card card">
        <h3 id="did-you-apply-title">Did you apply?</h3>
        <p className="muted">
          {label
            ? `Did you submit your application for ${label} on the job site?`
            : 'Did you submit your application on the job site?'}
        </p>
        <div className="modal-card__actions">
          <button type="button" className="btn-primary" onClick={onYes}>
            Yes, I applied
          </button>
          <button type="button" className="btn-secondary" onClick={onNo}>
            Not yet
          </button>
        </div>
      </div>
    </div>
  )
}
