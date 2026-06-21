import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import JobDescription from '../components/JobDescription'
import HelpButton from '../components/HelpButton'
import OnboardingGuide from '../components/OnboardingGuide'
import TailoredDocuments from '../components/TailoredDocuments'
import { useProfile } from '../ProfileContext'

const STATUS_OPTIONS = ['', 'discovered', 'tailored', 'applied', 'follow_up_sent', 'interview', 'rejected', 'replied']

const FIRST_APP_STEPS = [
  {
    step: 1,
    title: 'Upload your CV',
    body: 'Add your CV and cover letter in Profile so the AI can tailor documents for each role.',
    to: '/app/profile',
    linkLabel: 'Go to Profile →',
  },
  {
    step: 2,
    title: 'Search for jobs',
    body: 'Pick one location and run a search. New matches are saved here automatically.',
    to: '/app/jobs',
    linkLabel: 'Search jobs →',
  },
  {
    step: 3,
    title: 'Tailor your documents',
    body: 'Click Tailor on a job card. The AI rewrites your CV and cover letter for that role.',
  },
  {
    step: 4,
    title: 'Review & send',
    body: 'Open your tailored CV and cover letter, preview the email, then send outreach.',
  },
]

function hasTailoredDocs(app) {
  return Boolean(app.tailored_cv_path || app.tailored_cover_letter_path)
    || ['tailored', 'applied', 'follow_up_sent', 'interview', 'replied'].includes(app.status)
}

export default function Applications() {
  const { profile } = useProfile()
  const [applications, setApplications] = useState([])
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [actionMsg, setActionMsg] = useState(null)
  const [busy, setBusy] = useState(null)
  const [emailsByApp, setEmailsByApp] = useState({})
  const [expandedEmails, setExpandedEmails] = useState(null)
  const [contactsByApp, setContactsByApp] = useState({})
  const [expandedContacts, setExpandedContacts] = useState(null)
  const [loadingContacts, setLoadingContacts] = useState(null)
  const [expandedAnalysis, setExpandedAnalysis] = useState(null)
  const [expandedDesc, setExpandedDesc] = useState(null)
  const [expandedDocs, setExpandedDocs] = useState(null)
  const [selected, setSelected] = useState(new Set())
  const [viewMode, setViewMode] = useState('table')

  const parseAnalysis = (app) => {
    try {
      return app.analysis_json ? JSON.parse(app.analysis_json) : null
    } catch {
      return null
    }
  }

  const loadApps = useCallback(async () => {
    if (!profile?.id) return
    setLoading(true)
    try {
      const apps = await api.getApplications(filter || undefined)
      setApplications(apps)
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }, [profile, filter])

  useEffect(() => { loadApps() }, [loadApps])

  const handleAction = async (action, appId) => {
    setBusy(appId)
    setActionMsg(null)
    try {
      if (action === 'tailor') {
        const app = await api.tailorSingle(appId)
        setActionMsg({ type: 'success', text: 'Documents tailored. Open them below to review before sending.' })
        setExpandedDocs(appId)
      } else if (action === 'send') {
        await api.sendOutreach(appId, false)
        setActionMsg({ type: 'success', text: 'Outreach emails sent' })
      } else if (action === 'dry-run') {
        const emails = await api.sendOutreach(appId, true)
        setActionMsg({ type: 'info', text: `Preview ready for ${emails.length} email(s).` })
        await refreshEmails(appId, true)
      } else if (action === 'test') {
        const emails = await api.sendOutreach(appId, false, true)
        const result = emails[0]
        if (result?.status === 'test_sent') {
          setActionMsg({ type: 'success', text: `Test email sent to ${result.recipient_email}` })
        } else {
          setActionMsg({ type: 'error', text: `Test send failed: ${result?.error_message || 'unknown error'}` })
        }
        await refreshEmails(appId, true)
      } else if (action === 'follow-up') {
        await api.scheduleFollowUp(appId, 'Follow-up sent', 7)
        setActionMsg({ type: 'success', text: 'Follow-up scheduled' })
      }
      await loadApps()
    } catch (err) {
      setActionMsg({ type: 'error', text: err.message })
    }
    setBusy(null)
  }

  const handleBulkTailor = async () => {
    setBusy('bulk')
    try {
      const discovered = applications.filter((a) => a.status === 'discovered').map((a) => a.id)
      if (discovered.length === 0) {
        setActionMsg({ type: 'info', text: 'No discovered applications to tailor' })
      } else {
        const tailored = await api.tailorDocuments(discovered)
        setActionMsg({
          type: 'success',
          text: `Tailored ${tailored.length} application(s). Open each card to review CV and cover letter.`,
        })
        await loadApps()
      }
    } catch (err) {
      setActionMsg({ type: 'error', text: err.message })
    }
    setBusy(null)
  }

  const handleStatusChange = async (appId, status) => {
    await api.updateStatus(appId, status)
    await loadApps()
  }

  const handleBulkSend = async () => {
    const ids = applications.filter((a) => selected.has(a.id) && a.status === 'tailored').map((a) => a.id)
    if (ids.length === 0) {
      setActionMsg({ type: 'info', text: 'Select tailored applications to send outreach.' })
      return
    }
    if (!window.confirm(`Send outreach for ${ids.length} application(s)?`)) return
    setBusy('bulk-send')
    setActionMsg(null)
    try {
      const res = await api.sendOutreachBatch(ids)
      setActionMsg({
        type: res.failed ? 'info' : 'success',
        text: `Sent ${res.sent} application(s)${res.failed ? `, ${res.failed} failed` : ''}.`,
      })
      setSelected(new Set())
      await loadApps()
    } catch (err) {
      setActionMsg({ type: 'error', text: err.message })
    }
    setBusy(null)
  }

  const toggleSelect = (appId) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(appId)) next.delete(appId)
      else next.add(appId)
      return next
    })
  }

  const toggleSelectAll = () => {
    const tailored = applications.filter((a) => a.status === 'tailored')
    if (selected.size === tailored.length && tailored.length > 0) {
      setSelected(new Set())
    } else {
      setSelected(new Set(tailored.map((a) => a.id)))
    }
  }

  const handleClearAll = async () => {
    if (applications.length === 0) {
      setActionMsg({ type: 'info', text: 'No jobs to clear' })
      return
    }
    if (!window.confirm('Remove ALL jobs/applications for this profile? This cannot be undone.')) return
    setBusy('clear')
    setActionMsg(null)
    try {
      const res = await api.deleteAllApplications()
      setActionMsg({ type: 'success', text: `Removed ${res.deleted} job(s)` })
      await loadApps()
    } catch (err) {
      setActionMsg({ type: 'error', text: err.message })
    }
    setBusy(null)
  }

  const refreshEmails = async (appId, expand = false) => {
    try {
      const emails = await api.getOutreachEmails(appId)
      setEmailsByApp((prev) => ({ ...prev, [appId]: emails }))
      if (expand) setExpandedEmails(appId)
    } catch (err) {
      console.error(err)
    }
  }

  const toggleEmails = async (appId) => {
    if (expandedEmails === appId) {
      setExpandedEmails(null)
      return
    }
    setExpandedDesc(null)
    setExpandedContacts(null)
    setExpandedAnalysis(null)
    setExpandedDocs(null)
    await refreshEmails(appId, true)
  }

  const toggleContacts = async (appId) => {
    if (expandedContacts === appId) {
      setExpandedContacts(null)
      return
    }
    setExpandedContacts(appId)
    setExpandedDesc(null)
    setExpandedEmails(null)
    setExpandedAnalysis(null)
    setExpandedDocs(null)
    setLoadingContacts(appId)
    try {
      const contacts = await api.getContacts(appId)
      setContactsByApp((prev) => ({ ...prev, [appId]: contacts }))
    } catch (err) {
      setActionMsg({ type: 'error', text: `Could not find contacts: ${err.message}` })
    }
    setLoadingContacts(null)
  }


  const toggleDocs = (appId) => {
    setExpandedDocs((prev) => (prev === appId ? null : appId))
    setExpandedDesc(null)
    setExpandedEmails(null)
    setExpandedContacts(null)
    setExpandedAnalysis(null)
  }

  const toggleDesc = (appId) => {
    setExpandedDesc((prev) => (prev === appId ? null : appId))
    setExpandedDocs(null)
    setExpandedEmails(null)
    setExpandedContacts(null)
    setExpandedAnalysis(null)
  }

  const toggleAnalysis = (appId) => {
    setExpandedAnalysis((prev) => (prev === appId ? null : appId))
    setExpandedDocs(null)
    setExpandedDesc(null)
    setExpandedEmails(null)
    setExpandedContacts(null)
  }

  if (!profile) {
    return <div className="empty-state"><p>Create your profile first.</p></div>
  }

  const showOnboarding = applications.length === 0 || applications.every((a) => a.status === 'discovered')

  return (
    <div>
      <div className="page-header-row">
        <h2 className="page-title" style={{ marginBottom: 0 }}>Applications</h2>
        <div className="page-header-actions">
          <HelpButton
            className="btn-secondary"
            onClick={handleBulkTailor}
            disabled={busy === 'bulk'}
            title="Tailor All Discovered"
            help="Generates tailored CV and cover letter for every job still in discovered status."
          >
            Tailor All Discovered
          </HelpButton>
          <HelpButton
            className="btn-danger"
            onClick={handleClearAll}
            disabled={busy === 'clear' || applications.length === 0}
            title="Remove All Jobs"
            help="Permanently deletes every saved application."
          >
            {busy === 'clear' ? 'Clearing…' : 'Remove All'}
          </HelpButton>
        </div>
      </div>
      <p className="page-subtitle">
        Bulk-apply workflow: tailor documents in batch, review CV & cover letter previews, then send outreach to multiple jobs.
      </p>

      {showOnboarding && (
        <OnboardingGuide
          storageKey="jh_onboarding_first_app"
          title="Your first application in 4 steps"
          steps={FIRST_APP_STEPS}
        />
      )}

      {actionMsg && <div className={`alert alert-${actionMsg.type}`}>{actionMsg.text}</div>}

      <div className="applications-toolbar applications-toolbar--enhanced">
        <select value={filter} onChange={(e) => setFilter(e.target.value)} className="status-filter">
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{s ? s.replace('_', ' ') : 'All statuses'}</option>
          ))}
        </select>
        <div className="view-toggle">
          <button
            type="button"
            className={`btn-secondary btn-sm${viewMode === 'table' ? ' active' : ''}`}
            onClick={() => setViewMode('table')}
          >
            Table
          </button>
          <button
            type="button"
            className={`btn-secondary btn-sm${viewMode === 'cards' ? ' active' : ''}`}
            onClick={() => setViewMode('cards')}
          >
            Cards
          </button>
        </div>
        {selected.size > 0 && (
          <HelpButton
            className="btn-primary btn-sm"
            disabled={busy === 'bulk-send'}
            onClick={handleBulkSend}
            title="Send selected"
            help="Send outreach emails for all selected tailored applications."
          >
            {busy === 'bulk-send' ? 'Sending…' : `Send ${selected.size} selected`}
          </HelpButton>
        )}
      </div>

      {loading ? (
        <p>Loading...</p>
      ) : applications.length === 0 ? (
        <div className="empty-state">
          <p>No applications yet.</p>
          <p className="muted">Search for jobs and they will appear here automatically.</p>
        </div>
      ) : viewMode === 'table' ? (
        <div className="applications-table-wrap card">
          <table className="applications-table">
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    aria-label="Select all tailored"
                    checked={
                      applications.filter((a) => a.status === 'tailored').length > 0
                      && selected.size === applications.filter((a) => a.status === 'tailored').length
                    }
                    onChange={toggleSelectAll}
                  />
                </th>
                <th>Role</th>
                <th>Company</th>
                <th>Match</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {applications.map((app) => (
                <tr key={app.id} className={selected.has(app.id) ? 'applications-table__row--selected' : ''}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selected.has(app.id)}
                      disabled={app.status !== 'tailored'}
                      onChange={() => toggleSelect(app.id)}
                      aria-label={`Select ${app.job?.title}`}
                    />
                  </td>
                  <td>
                    <strong>{app.job?.title || 'Unknown'}</strong>
                    {app.job?.location && <div className="muted">{app.job.location}</div>}
                  </td>
                  <td>{app.job?.company}</td>
                  <td>{app.ai_match_score > 0 ? `${app.ai_match_score}/100` : '—'}</td>
                  <td><span className={`badge badge-${app.status}`}>{app.status.replace('_', ' ')}</span></td>
                  <td className="applications-table__actions">
                    {app.status === 'discovered' && (
                      <button type="button" className="btn-primary btn-sm" disabled={busy === app.id} onClick={() => handleAction('tailor', app.id)}>
                        Tailor
                      </button>
                    )}
                    {hasTailoredDocs(app) && (
                      <button type="button" className="btn-secondary btn-sm" onClick={() => toggleDocs(app.id)}>
                        Preview
                      </button>
                    )}
                    {app.status === 'tailored' && (
                      <button type="button" className="btn-primary btn-sm" disabled={busy === app.id} onClick={() => handleAction('send', app.id)}>
                        Send
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {applications.map((app) => (
            <TailoredDocuments
              key={`docs-${app.id}`}
              applicationId={app.id}
              open={expandedDocs === app.id}
              onClose={() => setExpandedDocs(null)}
            />
          ))}
        </div>
      ) : (
        <div className="application-list">
          {applications.map((app) => (
            <article key={app.id} className="application-card">
              <header className="application-card__header">
                <div className="application-card__info">
                  <h3>{app.job?.title || 'Unknown Role'}</h3>
                  <p className="application-card__meta">
                    {app.job?.company}
                    {app.job?.location && ` · ${app.job.location}`}
                    {app.ai_match_score > 0 && (
                      <span className="application-card__match"> · Match {app.ai_match_score}/100</span>
                    )}
                  </p>
                  <div className="application-card__tags">
                    <span className={`badge badge-${app.status}`}>{app.status.replace('_', ' ')}</span>
                    {app.job?.url && (
                      <a href={app.job.url} target="_blank" rel="noreferrer" className="application-card__link">
                        View listing →
                      </a>
                    )}
                  </div>
                </div>
                <select
                  className="status-select"
                  value={app.status}
                  onChange={(e) => handleStatusChange(app.id, e.target.value)}
                  aria-label="Application status"
                >
                  {STATUS_OPTIONS.filter(Boolean).map((s) => (
                    <option key={s} value={s}>{s.replace('_', ' ')}</option>
                  ))}
                </select>
              </header>

              {hasTailoredDocs(app) && (
                <div className="application-card__ready">
                  <span>Tailored documents ready</span>
                  <button
                    type="button"
                    className="btn-primary btn-sm"
                    onClick={() => toggleDocs(app.id)}
                  >
                    {expandedDocs === app.id ? 'Hide documents' : 'View CV & Cover Letter'}
                  </button>
                </div>
              )}

              <div className="application-card__primary">
                {app.status === 'discovered' && (
                  <HelpButton
                    className="btn-primary"
                    disabled={busy === app.id}
                    onClick={() => handleAction('tailor', app.id)}
                    title="Tailor documents"
                    help="AI rewrites your CV and cover letter for this specific job."
                  >
                    {busy === app.id ? 'Tailoring…' : '1. Tailor documents'}
                  </HelpButton>
                )}
                {app.status === 'tailored' && (
                  <>
                    <HelpButton
                      className="btn-primary"
                      disabled={busy === app.id}
                      onClick={() => handleAction('send', app.id)}
                      title="Send outreach"
                      help="Finds recruiter contacts and sends your tailored application."
                    >
                      {busy === app.id ? 'Sending…' : '3. Send outreach'}
                    </HelpButton>
                    <HelpButton
                      className="btn-secondary"
                      disabled={busy === app.id}
                      onClick={() => handleAction('test', app.id)}
                      title="Send test to me"
                      help="Sends a copy to your own inbox so you can review formatting."
                    >
                      Send test to me
                    </HelpButton>
                  </>
                )}
                {(app.status === 'applied' || app.status === 'follow_up_sent') && (
                  <HelpButton
                    className="btn-secondary"
                    disabled={busy === app.id}
                    onClick={() => handleAction('follow-up', app.id)}
                    title="Log follow-up"
                    help="Records a follow-up and schedules the next reminder."
                  >
                    Log follow-up
                  </HelpButton>
                )}
              </div>

              <details className="application-card__more">
                <summary>More options</summary>
                <div className="application-card__more-actions">
                  {app.status === 'tailored' && (
                    <HelpButton
                      className="btn-secondary btn-sm"
                      disabled={busy === app.id}
                      onClick={() => handleAction('dry-run', app.id)}
                      title="Preview email"
                      help="Shows the outreach email without sending it."
                    >
                      Preview email
                    </HelpButton>
                  )}
                  {hasTailoredDocs(app) && (
                    <button
                      type="button"
                      className="btn-secondary btn-sm"
                      onClick={() => toggleDocs(app.id)}
                    >
                      View tailored docs
                    </button>
                  )}
                  {app.job?.description && (
                    <button
                      type="button"
                      className="btn-secondary btn-sm"
                      onClick={() => toggleDesc(app.id)}
                    >
                      {expandedDesc === app.id ? 'Hide description' : 'Job description'}
                    </button>
                  )}
                  {app.analysis_json && (
                    <button
                      type="button"
                      className="btn-secondary btn-sm"
                      onClick={() => toggleAnalysis(app.id)}
                    >
                      {expandedAnalysis === app.id ? 'Hide analysis' : 'AI match analysis'}
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    disabled={loadingContacts === app.id}
                    onClick={() => toggleContacts(app.id)}
                  >
                    {expandedContacts === app.id ? 'Hide contacts' : 'Find contacts'}
                  </button>
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    onClick={() => toggleEmails(app.id)}
                  >
                    {expandedEmails === app.id ? 'Hide emails' : 'View emails'}
                  </button>
                </div>
              </details>

              <TailoredDocuments
                applicationId={app.id}
                open={expandedDocs === app.id}
                onClose={() => setExpandedDocs(null)}
              />

              {expandedDesc === app.id && (
                <div className="application-card__panel">
                  <div className="application-card__panel-title">Job description</div>
                  <JobDescription html={app.job?.description} />
                </div>
              )}

              {expandedAnalysis === app.id && (() => {
                const a = parseAnalysis(app)
                if (!a) return <div className="application-card__panel"><p className="muted">No analysis available.</p></div>
                return (
                  <div className="application-card__panel">
                    <div className="application-card__panel-title">AI match — {a.match_score ?? app.ai_match_score}/100</div>
                    {Array.isArray(a.score_explanation) && a.score_explanation.map((b, i) => (
                      <div key={i} style={{ fontSize: '0.85rem', marginBottom: '0.4rem' }}>
                        <strong>{b.category}:</strong> {b.score}
                      </div>
                    ))}
                  </div>
                )
              })()}

              {expandedContacts === app.id && (
                <div className="application-card__panel">
                  <div className="application-card__panel-title">Contacts for {app.job?.company}</div>
                  {loadingContacts === app.id ? (
                    <p className="muted">Searching…</p>
                  ) : (contactsByApp[app.id] || []).length === 0 ? (
                    <p className="muted">No contacts found.</p>
                  ) : (
                    (contactsByApp[app.id] || []).map((c, i) => (
                      <div key={`${c.email}-${i}`} className="email-record">
                        <strong>{c.name || c.email}</strong>
                        {c.title && <span className="muted"> · {c.title}</span>}
                        <div><a href={`mailto:${c.email}`}>{c.email}</a></div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {expandedEmails === app.id && (
                <div className="application-card__panel">
                  <div className="application-card__panel-title">Outreach emails</div>
                  {(emailsByApp[app.id] || []).length === 0 ? (
                    <p className="muted">No emails yet. Preview or send outreach to create one.</p>
                  ) : (
                    (emailsByApp[app.id] || []).map((em) => (
                      <div key={em.id} className="email-record">
                        <span className={`badge badge-${em.status}`}>{em.status}</span>
                        <strong> {em.recipient_name || em.recipient_email}</strong>
                        <div className="muted" style={{ marginTop: '0.3rem' }}>{em.subject}</div>
                        <div className="email-body">{em.body}</div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
