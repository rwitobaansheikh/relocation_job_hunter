import { useEffect, useState } from 'react'
import { api } from '../api'
import ConfirmDialog from '../components/ConfirmDialog'
import useIsMobile from '../useIsMobile'

export default function Admin() {
  const isMobile = useIsMobile()
  const [users, setUsers] = useState([])
  const [stats, setStats] = useState(null)
  const [feedback, setFeedback] = useState([])
  const [message, setMessage] = useState(null)
  const [loading, setLoading] = useState(true)
  const [confirmDialog, setConfirmDialog] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const [u, s, f] = await Promise.all([api.getUsers(), api.getAdminStats(), api.getFeedback()])
      setUsers(u)
      setStats(s)
      setFeedback(f)
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
    setLoading(false)
  }

  const toggleApproved = async (item) => {
    try {
      await api.updateFeedback(item.id, { approved: !item.approved })
      await load()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
  }

  const removeFeedback = (item) => {
    const isReview = item.kind === 'review'
    setConfirmDialog({
      title: isReview ? 'Delete this review?' : 'Delete this message?',
      body: isReview
        ? 'It will be removed from the public feedback page immediately.'
        : "This can't be undone.",
      confirmLabel: isReview ? 'Delete review' : 'Delete message',
      danger: true,
      onConfirm: async () => {
        try {
          await api.deleteFeedback(item.id)
          await load()
        } catch (err) {
          setMessage({ type: 'error', text: err.message })
        }
      },
    })
  }

  useEffect(() => {
    load()
  }, [])

  const updateUser = async (id, data) => {
    setMessage(null)
    try {
      await api.updateUser(id, data)
      await load()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
  }

  const toggleKillSwitch = async () => {
    try {
      const s = await api.setKillSwitch(!stats.automation_globally_enabled)
      setStats(s)
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
  }

  if (loading) return <p>Loading...</p>

  return (
    <div>
      <h2 className="page-title">Admin</h2>
      <p className="page-subtitle">Manage users and the system</p>

      {message && <div className={`alert alert-${message.type}`}>{message.text}</div>}

      {stats && (
        <>
          <div className="stats-grid">
            <div className="stat-card"><div className="value">{stats.total_users}</div><div className="label">Total Users</div></div>
            <div className="stat-card"><div className="value">{stats.active_users}</div><div className="label">Active</div></div>
            <div className="stat-card"><div className="value">{stats.automation_users}</div><div className="label">Automation On</div></div>
            <div className="stat-card"><div className="value">{stats.total_applications}</div><div className="label">Applications</div></div>
            <div className="stat-card"><div className="value">{stats.emails_sent_today}</div><div className="label">Emails Today</div></div>
            <div className="stat-card"><div className="value">{stats.gemini_calls_today}</div><div className="label">LLM Calls Today</div></div>
            <div className="stat-card"><div className="value">{stats.rocketreach_calls_today}</div><div className="label">RocketReach Calls</div></div>
          </div>

          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ marginBottom: '0.6rem' }}>Global automation kill-switch</h3>
            <div className="switch-row">
              <span className={`badge badge-${stats.automation_globally_enabled ? 'applied' : 'rejected'}`}>
                {stats.automation_globally_enabled ? 'Enabled' : 'Disabled'}
              </span>
              <button
                className={stats.automation_globally_enabled ? 'btn-danger' : 'btn-primary'}
                onClick={toggleKillSwitch}
              >
                {stats.automation_globally_enabled ? 'Disable all automation' : 'Enable automation'}
              </button>
            </div>
            <p className="muted" style={{ marginTop: '0.5rem' }}>
              When disabled, the scheduler will not run any user's automation loop.
            </p>
          </div>
        </>
      )}

      <div className="card">
        <h3 style={{ marginBottom: '1rem' }}>Users</h3>
        {isMobile ? (
          <div className="mobile-row-list">
            {users.map((u) => (
              <div key={u.id} className="mobile-row-card">
                <div className="mobile-row-card__head">
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.92rem' }}>{u.profile_name || '-'}</div>
                    <div className="muted" style={{ fontSize: '0.8rem' }}>{u.email}</div>
                  </div>
                  <span className={`badge badge-${u.is_active ? 'applied' : 'rejected'}`}>
                    {u.is_active ? 'active' : 'disabled'}
                  </span>
                </div>
                <div className="mobile-row-card__meta">
                  <span style={{ textTransform: 'capitalize' }}>Plan: {u.plan || '-'}</span>
                  <span>Apps: {u.application_count}</span>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', margin: 0, textTransform: 'none' }}>
                    <input
                      type="checkbox"
                      style={{ width: '1.1rem', height: '1.1rem' }}
                      checked={!!u.unlimited_access}
                      onChange={(e) => updateUser(u.id, { unlimited_access: e.target.checked })}
                    />
                    Unlimited
                  </label>
                </div>
                <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
                  <select
                    value={u.role}
                    style={{ width: 'auto', flex: 1 }}
                    onChange={(e) => updateUser(u.id, { role: e.target.value })}
                  >
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                  </select>
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    onClick={() => updateUser(u.id, { is_active: !u.is_active })}
                  >
                    {u.is_active ? 'Disable' : 'Enable'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Name</th>
                <th>Role</th>
                <th>Plan</th>
                <th>Apps</th>
                <th>Sent</th>
                <th>Unlimited</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>{u.profile_name || '-'}</td>
                  <td>
                    <select value={u.role} onChange={(e) => updateUser(u.id, { role: e.target.value })}>
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                    </select>
                  </td>
                  <td style={{ textTransform: 'capitalize' }}>{u.plan || '-'}</td>
                  <td>{u.application_count}</td>
                  <td>{u.emails_sent}</td>
                  <td>
                    <label className="switch-row" style={{ margin: 0 }}>
                      <input
                        type="checkbox"
                        checked={!!u.unlimited_access}
                        onChange={(e) => updateUser(u.id, { unlimited_access: e.target.checked })}
                      />
                    </label>
                  </td>
                  <td>
                    <span className={`badge badge-${u.is_active ? 'applied' : 'rejected'}`}>
                      {u.is_active ? 'active' : 'disabled'}
                    </span>
                  </td>
                  <td>
                    <button
                      className="btn-secondary"
                      style={{ fontSize: '0.78rem', padding: '0.3rem 0.6rem' }}
                      onClick={() => updateUser(u.id, { is_active: !u.is_active })}
                    >
                      {u.is_active ? 'Disable' : 'Enable'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        )}
      </div>

      <div className="card" style={{ marginTop: '1.5rem' }}>
        <h3 style={{ marginBottom: '1rem' }}>Reviews & contact messages</h3>
        {feedback.length === 0 ? (
          <p className="muted">No reviews or contact messages yet.</p>
        ) : isMobile ? (
          <div className="mobile-row-list">
            {feedback.map((f) => (
              <div key={f.id} className="mobile-row-card">
                <div className="mobile-row-card__head">
                  <span className="badge badge-pending">{f.kind}</span>
                  {f.rating ? <span style={{ color: 'var(--warning)' }}>{'★'.repeat(f.rating)}</span> : null}
                </div>
                <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>
                  {f.name}
                  {f.email && <div className="muted" style={{ fontSize: '0.78rem', fontWeight: 400 }}>{f.email}</div>}
                </div>
                <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
                  {f.subject && <strong>{f.subject}: </strong>}{f.message}
                </p>
                <div className="mobile-row-card__head">
                  {f.kind === 'review' ? (
                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', margin: 0, textTransform: 'none', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                      <input
                        type="checkbox"
                        style={{ width: '1.1rem', height: '1.1rem' }}
                        checked={!!f.approved}
                        onChange={() => toggleApproved(f)}
                      />
                      Visible
                    </label>
                  ) : <span />}
                  <button type="button" className="btn-danger btn-sm" onClick={() => removeFeedback(f)}>
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Type</th>
                  <th>From</th>
                  <th>Rating</th>
                  <th>Message</th>
                  <th>Visible</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {feedback.map((f) => (
                  <tr key={f.id}>
                    <td>{new Date(f.created_at).toLocaleString()}</td>
                    <td><span className="badge badge-pending">{f.kind}</span></td>
                    <td>
                      {f.name}
                      {f.email && <div className="muted" style={{ fontSize: '0.78rem' }}>{f.email}</div>}
                    </td>
                    <td>{f.rating ? '★'.repeat(f.rating) : '-'}</td>
                    <td className="muted" style={{ maxWidth: 320, whiteSpace: 'normal' }}>
                      {f.subject && <strong>{f.subject}: </strong>}{f.message}
                    </td>
                    <td>
                      {f.kind === 'review' ? (
                        <label className="switch-row" style={{ margin: 0 }}>
                          <input type="checkbox" checked={!!f.approved} onChange={() => toggleApproved(f)} />
                        </label>
                      ) : '-'}
                    </td>
                    <td>
                      <button
                        className="btn-danger"
                        style={{ fontSize: '0.78rem', padding: '0.3rem 0.6rem' }}
                        onClick={() => removeFeedback(f)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <ConfirmDialog dialog={confirmDialog} onCancel={() => setConfirmDialog(null)} />
    </div>
  )
}
