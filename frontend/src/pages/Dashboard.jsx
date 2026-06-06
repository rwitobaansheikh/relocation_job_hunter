import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useProfile } from '../ProfileContext'

export default function Dashboard() {
  const { profile, loading } = useProfile()
  const [stats, setStats] = useState(null)

  useEffect(() => {
    if (profile?.id) {
      api.getDashboardStats(profile.id).then(setStats).catch(console.error)
    }
  }, [profile])

  if (loading) return <p>Loading...</p>

  if (!profile) {
    return (
      <div className="empty-state">
        <h2 className="page-title">Welcome to Relocation Job Hunter</h2>
        <p className="page-subtitle">Create your profile to get started</p>
        <Link to="/profile"><button className="btn-primary">Set Up Profile</button></Link>
      </div>
    )
  }

  return (
    <div>
      <h2 className="page-title">Dashboard</h2>
      <p className="page-subtitle">Track your job hunt for {profile.full_name}</p>

      {stats && (
        <div className="stats-grid">
          <div className="stat-card"><div className="value">{stats.total}</div><div className="label">Total Jobs</div></div>
          <div className="stat-card"><div className="value">{stats.discovered}</div><div className="label">Discovered</div></div>
          <div className="stat-card"><div className="value">{stats.tailored}</div><div className="label">Tailored</div></div>
          <div className="stat-card"><div className="value">{stats.applied}</div><div className="label">Applied</div></div>
          <div className="stat-card"><div className="value">{stats.interview}</div><div className="label">Interviews</div></div>
          <div className="stat-card"><div className="value">{stats.needs_follow_up}</div><div className="label">Need Follow-up</div></div>
        </div>
      )}

      <div className="grid-2">
        <div className="card">
          <h3 style={{ marginBottom: '0.8rem' }}>Quick Actions</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <Link to="/jobs"><button className="btn-primary" style={{ width: '100%' }}>Search New Jobs</button></Link>
            <Link to="/applications"><button className="btn-secondary" style={{ width: '100%' }}>View Applications</button></Link>
            <Link to="/profile"><button className="btn-secondary" style={{ width: '100%' }}>Update Profile</button></Link>
          </div>
        </div>
        <div className="card">
          <h3 style={{ marginBottom: '0.8rem' }}>Profile Status</h3>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
            CV: {profile.cv_path ? '✓ Uploaded' : '✗ Not uploaded'}<br />
            Cover Letter: {profile.baseline_cover_letter_path ? '✓ Uploaded' : '✗ Not uploaded'}<br />
            Target Roles: {profile.target_roles || 'Not set'}<br />
            Target Countries: {profile.target_countries || 'Not set'}
          </p>
        </div>
      </div>
    </div>
  )
}
