import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { useProfile } from '../ProfileContext'

const STATUS_OPTIONS = ['', 'discovered', 'tailored', 'applied', 'follow_up_sent', 'interview', 'rejected', 'replied']

export default function Applications() {
  const { profile } = useProfile()
  const [applications, setApplications] = useState([])
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [actionMsg, setActionMsg] = useState(null)
  const [busy, setBusy] = useState(null)

  const loadApps = useCallback(async () => {
    if (!profile?.id) return
    setLoading(true)
    try {
      const apps = await api.getApplications(profile.id, filter || undefined)
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
        await api.tailorSingle(appId)
        setActionMsg({ type: 'success', text: 'Documents tailored successfully' })
      } else if (action === 'send') {
        await api.sendOutreach(appId, false)
        setActionMsg({ type: 'success', text: 'Outreach emails sent' })
      } else if (action === 'dry-run') {
        const emails = await api.sendOutreach(appId, true)
        setActionMsg({ type: 'info', text: `Dry run: would send to ${emails.length} contacts` })
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
        await api.tailorDocuments(discovered)
        setActionMsg({ type: 'success', text: `Tailored ${discovered.length} applications` })
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

  if (!profile) {
    return <div className="empty-state"><p>Create your profile first.</p></div>
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <h2 className="page-title">Applications</h2>
        <button className="btn-secondary" onClick={handleBulkTailor} disabled={busy === 'bulk'}>
          Tailor All Discovered
        </button>
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
                    <button className="btn-primary" disabled={busy === app.id} onClick={() => handleAction('send', app.id)}>
                      Send Outreach
                    </button>
                  </>
                )}
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
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
