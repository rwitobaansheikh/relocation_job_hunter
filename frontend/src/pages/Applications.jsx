import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import ApplyOnSiteButton from '../components/ApplyOnSiteButton'
import DidYouApplyModal from '../components/DidYouApplyModal'
import JobDescription from '../components/JobDescription'
import HelpButton from '../components/HelpButton'
import OnboardingGuide from '../components/OnboardingGuide'
import OutreachDraftPanel from '../components/OutreachDraftPanel'
import TailoredDocuments from '../components/TailoredDocuments'
import { useProfile } from '../ProfileContext'

const STATUS_OPTIONS = ['', 'discovered', 'tailored', 'applied', 'follow_up_sent', 'interview', 'rejected', 'replied']

const FIRST_APP_STEPS = [
  {
    step: 1,
    title: 'Upload your CV',
    body: 'Add your CV in Profile so the AI can tailor an ATS-friendly version for each role.',
    to: '/app/profile',
    linkLabel: 'Go to Profile →',
  },
  {
    step: 2,
    title: 'Search jobs in one place',
    body: 'Run a search across LinkedIn, RemoteOK, Remotive, and more. Matches save here automatically.',
    to: '/app/jobs',
    linkLabel: 'Search jobs →',
  },
  {
    step: 3,
    title: 'Tailor CV & cover letter',
    body: 'Generate role-specific documents for each job — preview, edit, and download as Word files.',
  },
  {
    step: 4,
    title: 'Apply on the job site',
    body: 'Open the listing, upload your tailored documents, and mark the application as applied when done.',
  },
  {
    step: 5,
    title: 'Optional: outreach draft',
    body: 'Generate a cold email draft to copy into your own inbox — the app never sends email for you.',
  },
  {
    step: 6,
    title: 'Track status',
    body: 'Mark applications as applied, rejected, or follow up as you hear back.',
  },
]

function hasTailoredDocs(app) {
  return Boolean(app.tailored_cv_path || app.tailored_cover_letter_path)
    || ['tailored', 'applied', 'follow_up_sent', 'interview', 'replied'].includes(app.status)
}

export default function Applications() {
  const navigate = useNavigate()
  const { profile } = useProfile()
  const [applications, setApplications] = useState([])
  const [filter, setFilter] = useState('')
  const [sortBy, setSortBy] = useState('match')
  const [queueFilter, setQueueFilter] = useState('')
  const [automationBatches, setAutomationBatches] = useState([])
  const [loading, setLoading] = useState(true)
  const [actionMsg, setActionMsg] = useState(null)
  const [busy, setBusy] = useState(null)
  const [applyPrompt, setApplyPrompt] = useState(null)
  const [expandedAnalysis, setExpandedAnalysis] = useState(null)
  const [expandedDesc, setExpandedDesc] = useState(null)
  const [expandedDocs, setExpandedDocs] = useState(null)
  const [expandedDraft, setExpandedDraft] = useState(null)
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
      const options = {}
      if (queueFilter === 'manual') options.manualOnly = true
      else if (queueFilter.startsWith('auto:')) options.automationBatch = queueFilter.slice(5)
      const apps = await api.getApplications(filter || undefined, sortBy || undefined, options)
      setApplications(apps)
      const batches = await api.getAutomationBatches().catch(() => [])
      setAutomationBatches(batches)
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }, [profile, filter, sortBy, queueFilter])

  useEffect(() => { loadApps() }, [loadApps])

  const handleTailor = async (appId) => {
    setBusy(appId)
    setActionMsg(null)
    try {
      await api.tailorSingle(appId)
      setActionMsg({ type: 'success', text: 'Documents ready — preview, download, then apply on the job site.' })
      setExpandedDocs(appId)
      await loadApps()
    } catch (err) {
      setActionMsg({ type: 'error', text: err.message })
    }
    setBusy(null)
  }

  const handleManualApply = (app) => {
    const url = app.job?.url
    if (!url) {
      setActionMsg({ type: 'error', text: 'This job has no listing URL. Add one via Jobs → Import link.' })
      return
    }
    setActionMsg(null)
    window.open(url, '_blank', 'noopener,noreferrer')
    setApplyPrompt(app)
  }

  const handleApplyConfirmed = async () => {
    if (!applyPrompt) return
    const app = applyPrompt
    setApplyPrompt(null)
    if (['applied', 'interview', 'replied'].includes(app.status)) {
      return
    }
    setBusy(`apply-${app.id}`)
    try {
      await api.updateStatus(app.id, 'applied')
      setActionMsg({
        type: 'success',
        text: 'Marked as applied. Upload your tailored CV and cover letter if you have not already.',
      })
      await loadApps()
    } catch (err) {
      setActionMsg({ type: 'error', text: err.message })
    }
    setBusy(null)
  }

  const handleApplyDismissed = () => {
    setApplyPrompt(null)
    setActionMsg({ type: 'info', text: 'Job listing opened in a new tab.' })
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
          text: `Tailored ${tailored.length} application(s). Download docs and apply on each job site.`,
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

  const handleReject = async (app) => {
    if (app.status === 'rejected') return
    setBusy(`reject-${app.id}`)
    setActionMsg(null)
    try {
      await api.updateStatus(app.id, 'rejected')
      setActionMsg({
        type: 'success',
        text: `Moved "${app.job?.title || 'application'}" to rejected.`,
      })
      await loadApps()
    } catch (err) {
      setActionMsg({ type: 'error', text: err.message })
    }
    setBusy(null)
  }

  const handleDelete = async (app) => {
    const label = app.job?.title || 'this application'
    if (!window.confirm(`Delete "${label}" permanently? This removes the application and any tailored documents.`)) {
      return
    }
    setBusy(`delete-${app.id}`)
    setActionMsg(null)
    try {
      await api.deleteApplication(app.id)
      if (expandedDocs === app.id) setExpandedDocs(null)
      if (expandedDesc === app.id) setExpandedDesc(null)
      if (expandedAnalysis === app.id) setExpandedAnalysis(null)
      if (expandedDraft === app.id) setExpandedDraft(null)
      setActionMsg({ type: 'success', text: `Removed "${label}".` })
      await loadApps()
    } catch (err) {
      setActionMsg({ type: 'error', text: err.message })
    }
    setBusy(null)
  }

  const renderManageButtons = (app, compact = false) => (
    <>
      {app.status !== 'rejected' && (
        <HelpButton
          className={`btn-secondary${compact ? ' btn-sm' : ''}`}
          disabled={busy === `reject-${app.id}`}
          onClick={() => handleReject(app)}
          title="Mark rejected"
          help="Move this application to your rejected pile when you're not pursuing the role."
        >
          {busy === `reject-${app.id}` ? 'Updating…' : 'Mark rejected'}
        </HelpButton>
      )}
      <HelpButton
        className={`btn-danger${compact ? ' btn-sm' : ''}`}
        disabled={busy === `delete-${app.id}`}
        onClick={() => handleDelete(app)}
        title="Delete application"
        help="Permanently removes this job application and its tailored documents."
      >
        {busy === `delete-${app.id}` ? 'Deleting…' : 'Delete'}
      </HelpButton>
    </>
  )

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

  const toggleDocs = (appId) => {
    setExpandedDocs((prev) => (prev === appId ? null : appId))
    setExpandedDesc(null)
    setExpandedAnalysis(null)
    setExpandedDraft(null)
  }

  const toggleDraft = (appId) => {
    setExpandedDraft((prev) => (prev === appId ? null : appId))
    setExpandedDesc(null)
    setExpandedAnalysis(null)
    setExpandedDocs(null)
  }

  const toggleDesc = (appId) => {
    setExpandedDesc((prev) => (prev === appId ? null : appId))
    setExpandedDocs(null)
    setExpandedAnalysis(null)
    setExpandedDraft(null)
  }

  const toggleAnalysis = (appId) => {
    setExpandedAnalysis((prev) => (prev === appId ? null : appId))
    setExpandedDocs(null)
    setExpandedDesc(null)
    setExpandedDraft(null)
  }

  const renderExpandedPanels = (app) => (
    <>
      <TailoredDocuments
        applicationId={app.id}
        jobUrl={app.job?.url}
        open={expandedDocs === app.id}
        onClose={() => setExpandedDocs(null)}
        onApply={() => handleManualApply(app)}
      />
      <OutreachDraftPanel
        applicationId={app.id}
        companyName={app.job?.company}
        jobTitle={app.job?.title}
        open={expandedDraft === app.id}
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
    </>
  )

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
        Search matches land here. Tailor CVs and cover letters, apply on job sites, and optionally draft outreach emails to send yourself.
      </p>

      {showOnboarding && (
        <OnboardingGuide
          storageKey="jh_onboarding_first_app"
          title="Your application workflow"
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
        <select value={queueFilter} onChange={(e) => setQueueFilter(e.target.value)} className="status-filter" aria-label="Application queue">
          <option value="">All jobs</option>
          <option value="manual">Manual searches only</option>
          {automationBatches.map((date) => (
            <option key={date} value={`auto:${date}`}>Automation · {date}</option>
          ))}
        </select>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="status-filter" aria-label="Sort applications">
          <option value="match">Highest match first</option>
          <option value="newest">Newest first</option>
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
      </div>

      {loading ? (
        <p>Loading...</p>
      ) : applications.length === 0 ? (
        <div className="empty-dashed">
          <p className="title">No applications yet</p>
          <p>Run a job search and matches will land here automatically.</p>
          <button type="button" className="btn-primary" onClick={() => navigate('/app/jobs')}>
            Search jobs
          </button>
        </div>
      ) : viewMode === 'table' ? (
        <div className="applications-table-wrap card">
          <table className="applications-table">
            <thead>
              <tr>
                <th>Role</th>
                <th>Company</th>
                <th>Match</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {applications.map((app) => (
                <tr key={app.id}>
                  <td>
                    <strong>{app.job?.title || 'Unknown'}</strong>
                    {app.job?.location && <div className="muted">{app.job.location}</div>}
                  </td>
                  <td>{app.job?.company}</td>
                  <td>{app.ai_match_score > 0 ? `${app.ai_match_score}/100` : '—'}</td>
                  <td><span className={`badge badge-${app.status}`}>{app.status.replace('_', ' ')}</span></td>
                  <td className="applications-table__actions">
                    {app.status === 'discovered' && (
                      <button type="button" className="btn-primary btn-sm" disabled={busy === app.id} onClick={() => handleTailor(app.id)}>
                        {busy === app.id ? 'Tailoring…' : 'Tailor'}
                      </button>
                    )}
                    {hasTailoredDocs(app) && (
                      <>
                        <button type="button" className="btn-secondary btn-sm" onClick={() => toggleDocs(app.id)}>
                          Docs
                        </button>
                        <button type="button" className="btn-secondary btn-sm" onClick={() => toggleDraft(app.id)}>
                          Email draft
                        </button>
                      </>
                    )}
                    <ApplyOnSiteButton
                      jobUrl={app.job?.url}
                      onApply={() => handleManualApply(app)}
                      busy={busy === `apply-${app.id}`}
                      className={hasTailoredDocs(app) ? 'btn-primary' : 'btn-secondary'}
                      size="btn-sm"
                      label={hasTailoredDocs(app) ? 'Apply on site' : 'View listing'}
                    />
                    {renderManageButtons(app, true)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {applications.map((app) => (
            <div key={`panels-${app.id}`}>{renderExpandedPanels(app)}</div>
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
                    {app.automation_batch_date && (
                      <span className="badge badge-discovered">Auto · {app.automation_batch_date}</span>
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
                  <span>Tailored CV & cover letter ready</span>
                  <button type="button" className="btn-secondary btn-sm" onClick={() => toggleDocs(app.id)}>
                    {expandedDocs === app.id ? 'Hide documents' : 'Preview & download'}
                  </button>
                </div>
              )}

              <div className="application-card__primary application-card__primary--apply">
                {app.status === 'discovered' && (
                  <HelpButton
                    className="btn-primary"
                    disabled={busy === app.id}
                    onClick={() => handleTailor(app.id)}
                    title="Tailor documents"
                    help="AI generates a CV360-style CV and cover letter tailored to this job."
                  >
                    {busy === app.id ? 'Tailoring…' : 'Tailor documents'}
                  </HelpButton>
                )}
                {hasTailoredDocs(app) && (
                  <>
                    <HelpButton
                      className="btn-secondary"
                      onClick={() => toggleDocs(app.id)}
                      title="Preview documents"
                      help="Review, edit, and download your tailored Word documents."
                    >
                      Preview & download
                    </HelpButton>
                    <HelpButton
                      className="btn-secondary"
                      onClick={() => toggleDraft(app.id)}
                      title="Generate outreach email"
                      help="Draft a cold email to copy into your inbox. The app does not send email."
                    >
                      Generate outreach email
                    </HelpButton>
                  </>
                )}
                <ApplyOnSiteButton
                  jobUrl={app.job?.url}
                  onApply={() => handleManualApply(app)}
                  busy={busy === `apply-${app.id}`}
                  className="btn-primary"
                  label={hasTailoredDocs(app) ? 'Apply on job site' : 'View job listing'}
                />
              </div>

              <details className="application-card__more">
                <summary>More options</summary>
                <div className="application-card__more-actions">
                  {app.job?.description && (
                    <button type="button" className="btn-secondary btn-sm" onClick={() => toggleDesc(app.id)}>
                      {expandedDesc === app.id ? 'Hide description' : 'Job description'}
                    </button>
                  )}
                  {app.analysis_json && (
                    <button type="button" className="btn-secondary btn-sm" onClick={() => toggleAnalysis(app.id)}>
                      {expandedAnalysis === app.id ? 'Hide analysis' : 'AI match analysis'}
                    </button>
                  )}
                </div>
              </details>

              <div className="application-card__manage">
                {renderManageButtons(app)}
              </div>

              {renderExpandedPanels(app)}
            </article>
          ))}
        </div>
      )}

      <DidYouApplyModal
        open={Boolean(applyPrompt)}
        jobTitle={applyPrompt?.job?.title}
        company={applyPrompt?.job?.company}
        onYes={handleApplyConfirmed}
        onNo={handleApplyDismissed}
      />
    </div>
  )
}
