import { useEffect, useState } from 'react'
import { api } from '../api'
import HelpButton from './HelpButton'

function verificationLabel(status, catchAll) {
  if (catchAll) return 'Catch-all (best guess)'
  if (status === 'accepted') return 'SMTP verified'
  if (status === 'found_on_site') return 'Found on website'
  if (status === 'pattern_guess') return 'Likely pattern'
  if (status === 'guess') return 'Unverified guess'
  if (status === 'error') return 'Could not verify'
  if (status) return status.replace(/_/g, ' ')
  return 'Unknown'
}

export default function OutreachPanel({ applicationId, open, companyDomain, onSent }) {
  const [contacts, setContacts] = useState(null)
  const [emails, setEmails] = useState(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const [info, setInfo] = useState(null)

  const loadHistory = async () => {
    try {
      const history = await api.getOutreachEmails(applicationId)
      setEmails(history)
    } catch {
      setEmails([])
    }
  }

  useEffect(() => {
    if (!open) return
    setContacts(null)
    setError(null)
    setInfo(null)
    loadHistory()
  }, [open, applicationId])

  const findContacts = async () => {
    setLoading(true)
    setError(null)
    setInfo('Searching for recruiters and verifying emails via SMTP — this can take a minute…')
    try {
      const found = await api.getContacts(applicationId)
      setContacts(found)
      if (found.length === 0) {
        setInfo('No contacts found. Add a company domain on the job or try a manual job import.')
      } else {
        setInfo(`Found ${found.length} contact(s).`)
      }
    } catch (err) {
      setError(err.message)
      setInfo(null)
    }
    setLoading(false)
  }

  const send = async (dryRun, testToSelf) => {
    const key = dryRun ? 'preview' : testToSelf ? 'test' : 'send'
    setBusy(key)
    setError(null)
    try {
      const results = await api.sendOutreach(applicationId, dryRun, testToSelf)
      await loadHistory()
      if (onSent) onSent()
      if (testToSelf) {
        setInfo('Preview sent from email@jobapplicationflow.com — check your inbox (and spam).')
      } else if (dryRun) {
        setInfo(`Preview ready for ${results.length} recipient(s) — nothing was sent.`)
      } else {
        setInfo(`Outreach sent to ${results.filter((r) => r.status === 'sent').length} recipient(s).`)
      }
    } catch (err) {
      setError(err.message)
    }
    setBusy(null)
  }

  if (!open) return null

  return (
    <div className="outreach-panel">
      <div className="outreach-panel__header">
        <div>
          <h4>Email outreach</h4>
          <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
            Find recruiter emails for {companyDomain ? `${companyDomain}` : 'this company'} and send your tailored CV & cover letter.
          </p>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {info && !error && <div className="alert alert-info">{info}</div>}

      <div className="outreach-panel__actions">
        <HelpButton
          className="btn-secondary btn-sm"
          disabled={loading || busy}
          onClick={findContacts}
          title="Find contacts"
          help="Searches LinkedIn for HR/recruiters, verifies email patterns against the company mail server, and checks generic inboxes like careers@ and jobs@."
        >
          {loading ? 'Finding contacts…' : contacts ? 'Refresh contacts' : 'Find contacts'}
        </HelpButton>
        <HelpButton
          className="btn-secondary btn-sm"
          disabled={!contacts?.length || busy}
          onClick={() => send(true, false)}
          title="Preview outreach"
          help="Generate outreach emails without sending — review subject and body below."
        >
          {busy === 'preview' ? 'Generating…' : 'Preview emails'}
        </HelpButton>
        <HelpButton
          className="btn-secondary btn-sm"
          disabled={busy}
          onClick={() => send(false, true)}
          title="Preview test email"
          help="Sends a preview to your inbox from email@jobapplicationflow.com with attachments. Real outreach to recruiters uses your login email."
        >
          {busy === 'test' ? 'Sending…' : 'Preview test email'}
        </HelpButton>
        <HelpButton
          className="btn-primary btn-sm"
          disabled={!contacts?.length || busy}
          onClick={() => {
            if (!window.confirm('Send outreach emails to the contacts below?')) return
            send(false, false)
          }}
          title="Send outreach"
          help="Sends outreach from your login email with your tailored CV and cover letter attached. Configure your mailbox in Settings."
        >
          {busy === 'send' ? 'Sending…' : 'Send outreach'}
        </HelpButton>
      </div>

      {contacts && contacts.length > 0 && (
        <div className="contact-list">
          <div className="outreach-panel__label">Contacts</div>
          {contacts.map((c, i) => (
            <div key={`${c.email}-${i}`} className="contact-card">
              <div className="contact-card__main">
                <strong>{c.name}</strong>
                <span className="muted">{c.title}</span>
              </div>
              <div className="contact-card__email">{c.email}</div>
              <div className="contact-card__meta">
                <span className={`badge badge-${['accepted', 'found_on_site'].includes(c.verification_status) ? 'applied' : c.verification_status === 'pattern_guess' ? 'discovered' : 'rejected'}`}>
                  {verificationLabel(c.verification_status, c.catch_all)}
                </span>
                {c.confidence > 0 && <span className="muted">{c.confidence}% confidence</span>}
                {c.pattern && <span className="muted">pattern: {c.pattern}</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {contacts && contacts.length === 0 && !loading && (
        <p className="muted">
          No contacts found yet. Add the company domain on the job (e.g. company.com), then try again —
          we scan their careers/contact pages and public listings for real addresses.
        </p>
      )}

      {emails && emails.length > 0 && (
        <div className="email-records">
          <div className="outreach-panel__label">Outreach history</div>
          {emails.map((e) => (
            <div key={e.id} className="email-record">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', flexWrap: 'wrap' }}>
                <strong>{e.recipient_name} &lt;{e.recipient_email}&gt;</strong>
                <span className={`badge badge-${e.status === 'sent' || e.status === 'test_sent' ? 'applied' : e.status === 'failed' ? 'rejected' : 'discovered'}`}>
                  {e.status.replace('_', ' ')}
                </span>
              </div>
              <div className="muted" style={{ fontSize: '0.85rem', marginTop: '0.25rem' }}>{e.subject}</div>
              {e.body && <div className="email-body">{e.body}</div>}
              {e.error_message && <div className="alert alert-error" style={{ marginTop: '0.5rem' }}>{e.error_message}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
