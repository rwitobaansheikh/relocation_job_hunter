import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Admin() {
  const [users, setUsers] = useState([])
  const [stats, setStats] = useState(null)
  const [feedback, setFeedback] = useState([])
  const [message, setMessage] = useState(null)
  const [loading, setLoading] = useState(true)

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

  const removeFeedback = async (item) => {
    if (!window.confirm('Delete this entry?')) return
    try {
      await api.deleteFeedback(item.id)
      await load()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
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
      </div>

      <div className="card" style={{ marginTop: '1.5rem' }}>
        <h3 style={{ marginBottom: '1rem' }}>Reviews & contact messages</h3>
        {feedback.length === 0 ? (
          <p className="muted">No feedback yet.</p>
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
    </div>
  )
}
