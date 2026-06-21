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

export default function OutreachPanel({
  applicationId,
  open,
  companyName,
  companyDomain,
  onSent,
  onDomainUpdated,
}) {
  const [contacts, setContacts] = useState(null)
  const [resolvedDomain, setResolvedDomain] = useState(companyDomain || '')
  const [domainInput, setDomainInput] = useState(companyDomain || '')
  const [domainWasJobBoard, setDomainWasJobBoard] = useState(false)
  const [emails, setEmails] = useState(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const [info, setInfo] = useState(null)

  useEffect(() => {
    setResolvedDomain(companyDomain || '')
    setDomainInput(companyDomain || '')
  }, [companyDomain])

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
    setDomainWasJobBoard(false)
    loadHistory()
  }, [open, applicationId])

  const saveDomain = async () => {
    const trimmed = domainInput.trim()
    if (!trimmed) return
    setBusy('domain')
    setError(null)
    try {
      const result = await api.updateCompanyDomain(applicationId, trimmed)
      setResolvedDomain(result.company_domain)
      setDomainInput(result.company_domain)
      if (onDomainUpdated) onDomainUpdated(result.company_domain)
      setInfo(`Employer domain set to ${result.company_domain}. Click Find contacts to search again.`)
    } catch (err) {
      setError(err.message)
    }
    setBusy(null)
  }

  const findContacts = async () => {
    setLoading(true)
    setError(null)
    setInfo('Resolving employer domain and searching for recruiter emails — this can take a minute…')
    try {
      const result = await api.getContacts(applicationId)
      setContacts(result.contacts)
      if (result.resolved_domain) {
        setResolvedDomain(result.resolved_domain)
        setDomainInput(result.resolved_domain)
        if (onDomainUpdated) onDomainUpdated(result.resolved_domain)
      }
      setDomainWasJobBoard(result.domain_was_job_board)

      if (result.contacts.length === 0) {
        const label = result.resolved_domain || companyName || 'this company'
        setInfo(
          result.domain_was_job_board
            ? `Previously used a job-board domain. Now searching ${label} — still no public emails found. Try correcting the domain below.`
            : `No public recruiter emails found for ${label}. Many companies only use contact forms — try correcting the domain or reaching out on LinkedIn.`,
        )
      } else {
        setInfo(`Found ${result.contacts.length} contact(s) for ${result.resolved_domain || companyName}.`)
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

  const displayCompany = companyName || 'this company'
  const displayDomain = resolvedDomain || companyDomain

  return (
    <div className="outreach-panel">
      <div className="outreach-panel__header">
        <div>
          <h4>Email outreach</h4>
          <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
            Find recruiter emails for <strong>{displayCompany}</strong>
            {displayDomain ? ` (${displayDomain})` : ''} and send your tailored CV & cover letter.
          </p>
        </div>
      </div>

      <div className="outreach-panel__domain" style={{ marginBottom: '0.75rem' }}>
        <label className="outreach-panel__label" htmlFor={`domain-${applicationId}`}>
          Employer domain
        </label>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            id={`domain-${applicationId}`}
            type="text"
            placeholder="company.com"
            value={domainInput}
            onChange={(e) => setDomainInput(e.target.value)}
            style={{ flex: '1 1 12rem', minWidth: '10rem' }}
          />
          <HelpButton
            className="btn-secondary btn-sm"
            disabled={busy === 'domain' || !domainInput.trim()}
            onClick={saveDomain}
            title="Save domain"
            help="Use the hiring company's website domain (e.g. fever.com), not the job board where you found the listing."
          >
            {busy === 'domain' ? 'Saving…' : 'Save domain'}
          </HelpButton>
        </div>
        {domainWasJobBoard && (
          <p className="muted" style={{ fontSize: '0.8rem', margin: '0.35rem 0 0' }}>
            The job listing URL pointed at a job board — we resolved the employer domain automatically.
          </p>
        )}
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {info && !error && <div className="alert alert-info">{info}</div>}

      <div className="outreach-panel__actions">
        <HelpButton
          className="btn-secondary btn-sm"
          disabled={loading || busy}
          onClick={findContacts}
          title="Find contacts"
          help="Resolves the employer domain, scans careers/contact pages, searches public listings, and optionally verifies email patterns."
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
          {busy === 'send' ? 'Sending outreach…' : 'Send outreach'}
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
          No public emails found for {displayDomain || displayCompany}. Confirm the employer domain above
          (not the job board), then refresh — we scan careers pages and public listings. Many companies
          only accept applications via their site or ATS.
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
