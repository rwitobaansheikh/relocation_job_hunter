export default function ConfirmDialog({ dialog, onCancel }) {
  if (!dialog) return null
  const { title, body, confirmLabel = 'Confirm', danger = false, onConfirm } = dialog

  const confirm = () => {
    onConfirm?.()
    onCancel()
  }

  return (
    <div className="confirm-overlay" onClick={onCancel}>
      <div
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
        className="confirm-box"
        onClick={(e) => e.stopPropagation()}
      >
        <h3>{title}</h3>
        <p>{body}</p>
        <div className="actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className={danger ? 'btn-danger-solid' : 'btn-primary'}
            onClick={confirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
