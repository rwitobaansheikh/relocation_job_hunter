import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import JobDescription from '../components/JobDescription'
import { useProfile } from '../ProfileContext'

const STATUS_OPTIONS = ['', 'discovered', 'tailored', 'applied', 'follow_up_sent', 'interview', 'rejected', 'replied']

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
        const usedAi = app.tailored_cv_path?.includes('/app_') || app.tailored_cv_path?.includes('generated/app_')
        setActionMsg({
          type: 'success',
          text: usedAi
            ? 'AI-tailored CV and cover letter generated for this role.'
            : 'Documents updated.',
        })
      } else if (action === 'send') {
        await api.sendOutreach(appId, false)
        setActionMsg({ type: 'success', text: 'Outreach emails sent' })
      } else if (action === 'dry-run') {
        const emails = await api.sendOutreach(appId, true)
        setActionMsg({ type: 'info', text: `Dry run: previewed ${emails.length} email(s). Click "View Emails" to read them.` })
        await refreshEmails(appId, true)
      } else if (action === 'test') {
        const emails = await api.sendOutreach(appId, false, true)
        const result = emails[0]
        if (result?.status === 'test_sent') {
          setActionMsg({ type: 'success', text: `Test email sent to your registered address (${result.recipient_email}). Check your inbox.` })
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
        if (tailored.length === 0) {
          setActionMsg({ type: 'info', text: 'No applications were tailored.' })
        } else if (tailored.length < discovered.length) {
          setActionMsg({
            type: 'success',
            text: `AI-tailored ${tailored.length} of ${discovered.length} applications. Retry the rest if the LLM was busy.`,
          })
        } else {
          setActionMsg({ type: 'success', text: `AI-tailored ${tailored.length} application(s).` })
        }
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

  const handleClearAll = async () => {
    if (applications.length === 0) {
      setActionMsg({ type: 'info', text: 'No jobs to clear' })
      return
    }
    if (!window.confirm('Remove ALL jobs/applications for this profile? This cannot be undone.')) {
      return
    }
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
    await refreshEmails(appId, true)
  }

  const toggleContacts = async (appId) => {
    if (expandedContacts === appId) {
      setExpandedContacts(null)
      return
    }
    setExpandedContacts(appId)
    // Fetch recruiting contacts via the built-in email scraper.
    setLoadingContacts(appId)
    try {
      const contacts = await api.getContacts(appId)
      setContactsByApp((prev) => ({ ...prev, [appId]: contacts }))
    } catch (err) {
      setActionMsg({ type: 'error', text: `Could not find contacts: ${err.message}` })
    }
    setLoadingContacts(null)
  }

  if (!profile) {
    return <div className="empty-state"><p>Create your profile first.</p></div>
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <h2 className="page-title">Applications</h2>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn-secondary" onClick={handleBulkTailor} disabled={busy === 'bulk'}>
            Tailor All Discovered
          </button>
          <button className="btn-danger" onClick={handleClearAll} disabled={busy === 'clear' || applications.length === 0}>
            {busy === 'clear' ? 'Clearing…' : 'Remove All Jobs'}
          </button>
        </div>
      </div>
      <p className="page-subtitle">Manage job applications, send outreach, and track follow-ups</p>

      {actionMsg && <div className={`alert alert-${actionMsg.type}`}>{actionMsg.text}</div>}

      <div style={{ marginBottom: '1.5rem' }}>
        <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: '200px' }}>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{s || 'All statuses'}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <p>Loading...</p>
      ) : applications.length === 0 ? (
        <div className="empty-state">
          <p>No applications yet. Search for jobs to get started.</p>
        </div>
      ) : (
        <div className="job-list">
          {applications.map((app) => (
            <div key={app.id} className="job-item">
              <div className="job-info">
                <h3>{app.job?.title || 'Unknown Role'}</h3>
                <div className="meta">
                  {app.job?.company} · {app.job?.location} · Score: {app.job?.relevance_score}
                  {app.job?.seniority_level && app.job.seniority_level !== 'unspecified' && (
                    ` · ${app.job.seniority_level}`
                  )}
                  {app.job?.salary_text && ` · ${app.job.salary_text}`}
                  {app.ai_match_score > 0 && (
                    <strong style={{ color: 'var(--accent)' }}> · AI Match: {app.ai_match_score}/100</strong>
                  )}
                  {app.job?.relocation_keywords && ` · Relocation: ${app.job.relocation_keywords}`}
                </div>
                <div style={{ marginTop: '0.4rem' }}>
                  <span className={`badge badge-${app.status}`}>{app.status.replace('_', ' ')}</span>
                  {app.next_follow_up_at && (
                    <span style={{ marginLeft: '0.5rem', fontSize: '0.8rem', color: 'var(--warning)' }}>
                      Follow-up: {new Date(app.next_follow_up_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
                {app.job?.url && (
                  <a href={app.job.url} target="_blank" rel="noreferrer" style={{ fontSize: '0.85rem' }}>
                    View listing →
                  </a>
                )}
              </div>
              <div className="job-actions">
                {app.status === 'discovered' && (
                  <button className="btn-secondary" disabled={busy === app.id} onClick={() => handleAction('tailor', app.id)}>
                    Tailor Docs
                  </button>
                )}
                {app.status === 'tailored' && (
                  <>
                    <button className="btn-secondary" disabled={busy === app.id} onClick={() => handleAction('dry-run', app.id)}>
                      Preview Email
                    </button>
                    <button className="btn-secondary" disabled={busy === app.id} onClick={() => handleAction('test', app.id)}>
                      Send Test to Me
                    </button>
                    <button className="btn-primary" disabled={busy === app.id} onClick={() => handleAction('send', app.id)}>
                      Send Outreach
                    </button>
                  </>
                )}
                {app.job?.description && (
                  <button className="btn-secondary" onClick={() => setExpandedDesc(expandedDesc === app.id ? null : app.id)}>
                    {expandedDesc === app.id ? 'Hide Description' : 'View Description'}
                  </button>
                )}
                {app.analysis_json && (
                  <button className="btn-secondary" onClick={() => setExpandedAnalysis(expandedAnalysis === app.id ? null : app.id)}>
                    {expandedAnalysis === app.id ? 'Hide Analysis' : 'View Analysis'}
                  </button>
                )}
                <button className="btn-secondary" disabled={loadingContacts === app.id} onClick={() => toggleContacts(app.id)}>
                  {expandedContacts === app.id ? 'Hide Contacts' : 'Find Contacts'}
                </button>
                <button className="btn-secondary" disabled={busy === app.id} onClick={() => toggleEmails(app.id)}>
                  {expandedEmails === app.id ? 'Hide Emails' : 'View Emails'}
                </button>
                {(app.status === 'applied' || app.status === 'follow_up_sent') && (
                  <button className="btn-secondary" disabled={busy === app.id} onClick={() => handleAction('follow-up', app.id)}>
                    Log Follow-up
                  </button>
                )}
                <select
                  value={app.status}
                  onChange={(e) => handleStatusChange(app.id, e.target.value)}
                  style={{ width: 'auto', fontSize: '0.8rem' }}
                >
                  {STATUS_OPTIONS.filter(Boolean).map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>

              {expandedDesc === app.id && (
                <div className="email-records">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '0.5rem', marginBottom: '0.5rem' }}>
                    <div style={{ fontSize: '0.95rem', fontWeight: 600 }}>Job Description</div>
                    {app.job?.url && (
                      <a href={app.job.url} target="_blank" rel="noreferrer" style={{ fontSize: '0.85rem' }}>
                        Open original post →
                      </a>
                    )}
                  </div>
                  {app.job?.salary_text && (
                    <div style={{ fontSize: '0.85rem', marginBottom: '0.5rem', color: 'var(--text-muted)' }}>
                      <strong>Salary:</strong> {app.job.salary_text}
                    </div>
                  )}
                  <JobDescription html={app.job?.description} />
                </div>
              )}

              {expandedAnalysis === app.id && (() => {
                const a = parseAnalysis(app)
                if (!a) return <div className="email-records"><p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No analysis available.</p></div>
                return (
                  <div className="email-records">
                    <div style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                      AI Match Analysis — {a.match_score ?? app.ai_match_score}/100
                    </div>
                    {Array.isArray(a.score_explanation) && a.score_explanation.length > 0 && (
                      <div style={{ marginBottom: '0.8rem' }}>
                        {a.score_explanation.map((b, i) => (
                          <div key={i} style={{ fontSize: '0.82rem', marginBottom: '0.3rem' }}>
                            <strong>{b.category}:</strong> {b.score}
                            {Array.isArray(b.evidence) && b.evidence.length > 0 && (
                              <ul style={{ margin: '0.2rem 0 0 1.1rem', color: 'var(--text-muted)' }}>
                                {b.evidence.map((ev, j) => <li key={j}>{ev}</li>)}
                              </ul>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                    {Array.isArray(a.gaps_and_suggestions) && a.gaps_and_suggestions.length > 0 && (
                      <div style={{ marginBottom: '0.8rem' }}>
                        <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Gaps & Suggestions</div>
                        <ul style={{ margin: '0.2rem 0 0 1.1rem', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                          {a.gaps_and_suggestions.map((g, i) => (
                            <li key={i}><strong>{g.gap}</strong>{g.suggestion ? ` — ${g.suggestion}` : ''}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {Array.isArray(a.red_flags) && a.red_flags.length > 0 && (
                      <div>
                        <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--danger, #f87171)' }}>Red Flags</div>
                        <ul style={{ margin: '0.2rem 0 0 1.1rem', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                          {a.red_flags.map((r, i) => <li key={i}>{r}</li>)}
                        </ul>
                      </div>
                    )}
                  </div>
                )
              })()}

              {expandedContacts === app.id && (
                <div className="email-records">
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                    Outreach contacts for {app.job?.company}
                  </div>
                  {loadingContacts === app.id ? (
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Searching for contacts…</p>
                  ) : (contactsByApp[app.id] || []).length === 0 ? (
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      No contacts found for this company.
                    </p>
                  ) : (
                    (contactsByApp[app.id] || []).map((c, i) => (
                      <div key={`${c.email}-${i}`} className="email-record" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.5rem' }}>
                        <div style={{ fontSize: '0.85rem' }}>
                          <strong>{c.name || '(no name)'}</strong>
                          {c.title && <span style={{ color: 'var(--text-muted)' }}> · {c.title}</span>}
                          <div>
                            <a href={`mailto:${c.email}`}>{c.email}</a>
                          </div>
                        </div>
                        {c.confidence > 0 && (
                          <span className="badge" style={{ flexShrink: 0 }}>{c.confidence}% confidence</span>
                        )}
                      </div>
                    ))
                  )}
                </div>
              )}

              {expandedEmails === app.id && (
                <div className="email-records">
                  {(emailsByApp[app.id] || []).length === 0 ? (
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      No emails recorded yet. Use “Preview Email”, “Send Test to Me”, or “Send Outreach”.
                    </p>
                  ) : (
                    (emailsByApp[app.id] || []).map((em) => (
                      <div key={em.id} className="email-record">
                        <div style={{ fontSize: '0.85rem' }}>
                          <span className={`badge badge-${em.status}`}>{em.status.replace('_', ' ')}</span>
                          <strong style={{ marginLeft: '0.5rem' }}>{em.recipient_name || em.recipient_email}</strong>
                          {' '}&lt;{em.recipient_email}&gt;
                          {em.sent_at && (
                            <span style={{ marginLeft: '0.5rem', color: 'var(--text-muted)' }}>
                              · {new Date(em.sent_at).toLocaleString()}
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: '0.85rem', marginTop: '0.3rem' }}>
                          <strong>Subject:</strong> {em.subject}
                        </div>
                        {em.error_message && (
                          <div style={{ fontSize: '0.8rem', color: 'var(--danger, #f87171)', marginTop: '0.3rem' }}>
                            Error: {em.error_message}
                          </div>
                        )}
                        <div className="email-body">{em.body}</div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
