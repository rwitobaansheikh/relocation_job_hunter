import { useEffect, useState } from 'react'
import { api } from '../api'
import HelpButton from './HelpButton'

export default function OutreachDraftPanel({
  applicationId,
  open,
  companyName,
  jobTitle,
}) {
  const [draft, setDraft] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!open) {
      setDraft(null)
      setError(null)
      setCopied(false)
    }
  }, [open, applicationId])

  const generate = async () => {
    setBusy(true)
    setError(null)
    setCopied(false)
    try {
      const result = await api.generateOutreachDraft(applicationId)
      setDraft(result)
    } catch (err) {
      setError(err.message)
    }
    setBusy(false)
  }

  const copyAll = async () => {
    if (!draft) return
    const text = `Subject: ${draft.subject}\n\n${draft.body}`
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
    } catch {
      setError('Could not copy to clipboard — select the text and copy manually.')
    }
  }

  if (!open) return null

  const label = [jobTitle, companyName].filter(Boolean).join(' at ')

  return (
    <div className="outreach-panel">
      <div className="outreach-panel__header">
        <div>
          <h4>Outreach email draft</h4>
          <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
            {label
              ? `Draft a cold email for ${label}. Copy it into your email client and send manually with your tailored attachments.`
              : 'Draft a cold outreach email to copy and send from your own inbox.'}
          </p>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="outreach-panel__actions">
        <HelpButton
          className="btn-primary btn-sm"
          disabled={busy}
          onClick={generate}
          title="Generate outreach email"
          help="Creates a tailored subject and body using your CV and this job. Nothing is sent from the app."
        >
          {busy ? 'Generating…' : draft ? 'Regenerate draft' : 'Generate outreach email'}
        </HelpButton>
        {draft && (
          <HelpButton
            className="btn-secondary btn-sm"
            onClick={copyAll}
            title="Copy to clipboard"
            help="Copy the subject and body so you can paste into Gmail, Outlook, or another mail client."
          >
            {copied ? 'Copied!' : 'Copy email'}
          </HelpButton>
        )}
      </div>

      {draft && (
        <div className="email-records" style={{ marginTop: '0.75rem' }}>
          <div className="outreach-panel__label">Subject</div>
          <div className="email-record" style={{ marginBottom: '0.75rem' }}>
            <strong>{draft.subject}</strong>
          </div>
          <div className="outreach-panel__label">Body</div>
          <div className="email-record">
            <div className="email-body" style={{ whiteSpace: 'pre-wrap' }}>{draft.body}</div>
          </div>
          <p className="muted" style={{ fontSize: '0.85rem', marginTop: '0.75rem' }}>
            Attach your tailored CV and cover letter from this app before sending.
          </p>
        </div>
      )}
    </div>
  )
}
