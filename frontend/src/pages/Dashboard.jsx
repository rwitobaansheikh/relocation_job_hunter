import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import OnboardingGuide from '../components/OnboardingGuide'
import { useProfile } from '../ProfileContext'
import HelpButton from '../components/HelpButton'

const DASHBOARD_STEPS = [
  {
    step: 1,
    title: 'Set up your profile',
    body: 'Upload your CV and cover letter, then add target roles and countries.',
    to: '/app/profile',
    linkLabel: 'Open Profile →',
  },
  {
    step: 2,
    title: 'Search for one location',
    body: 'Run a job search for a single country or city. Results save to Applications.',
    to: '/app/jobs',
    linkLabel: 'Search jobs →',
  },
  {
    step: 3,
    title: 'Tailor & apply',
    body: 'Tailor documents for a role, review your CV and cover letter, then send outreach.',
    to: '/app/applications',
    linkLabel: 'Go to Applications →',
  },
]

export default function Dashboard() {
  const { profile, loading } = useProfile()
  const [stats, setStats] = useState(null)
  const [billing, setBilling] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (profile?.id) {
      api.getDashboardStats().then(setStats).catch(console.error)
      api.getBilling().then(setBilling).catch(console.error)
    }
  }, [profile])

  if (loading) return <p>Loading...</p>

  if (!profile) {
    return (
      <div className="empty-state">
        <h2 className="page-title">Welcome to Job Application Flow</h2>
        <p className="page-subtitle">Complete your profile to get started</p>
        <HelpButton
          className="btn-primary"
          onClick={() => navigate('/app/profile')}
          title="Set Up Profile"
          help="Create your profile with CV, cover letter, and target roles so the app can search and tailor applications for you."
        >
          Set Up Profile
        </HelpButton>
      </div>
    )
  }

  return (
    <div>
      <h2 className="page-title">Dashboard</h2>
      <p className="page-subtitle">Track your job hunt for {profile.full_name}</p>

      {(stats?.total === 0 || !stats) && (
        <OnboardingGuide
          storageKey="jh_onboarding_dashboard"
          title="Welcome — here’s how to land your first application"
          steps={DASHBOARD_STEPS}
        />
      )}

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
            <HelpButton
              className="btn-primary"
              style={{ width: '100%' }}
              onClick={() => navigate('/app/jobs')}
              title="Search New Jobs"
              help="Open the job search page to find up to 100 matching roles from multiple boards, filtered by your CV and preferences."
            >
              Search New Jobs
            </HelpButton>
            <HelpButton
              className="btn-secondary"
              style={{ width: '100%' }}
              onClick={() => navigate('/app/applications')}
              title="View Applications"
              help="See every job you've saved, tailor documents, preview emails, and send outreach from one place."
            >
              View Applications
            </HelpButton>
            <HelpButton
              className="btn-secondary"
              style={{ width: '100%' }}
              onClick={() => navigate('/app/profile')}
              title="Update Profile"
              help="Edit your name, skills, target roles, countries, and re-upload your CV or cover letter."
            >
              Update Profile
            </HelpButton>
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

      {billing && (
        <div className="card" style={{ marginTop: '1.5rem' }}>
          <h3 style={{ marginBottom: '0.8rem' }}>Plan & Automation</h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.6rem' }}>
            <span className="badge badge-applied" style={{ textTransform: 'capitalize' }}>{billing.plan}</span>
            {billing.plan === 'trial' && <span className="muted">{billing.trial_days_left} day(s) of trial left</span>}
            <Link to="/app/automation" style={{ fontSize: '0.85rem' }}>Manage loops →</Link>
            <Link to="/app/billing" style={{ fontSize: '0.85rem' }}>Plan & Billing →</Link>
          </div>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
            {billing.usage.loops_active} / {billing.limits.max_loops} automation loops active ·
            {' '}{billing.usage.manual_today} / {billing.limits.manual_per_day} manual applications today
          </p>
        </div>
      )}
    </div>
  )
}
