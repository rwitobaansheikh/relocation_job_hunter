import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useProfile } from '../ProfileContext'
import HelpButton from '../components/HelpButton'

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

  const step1Done = Boolean(profile.cv_path && profile.baseline_cover_letter_path)
  const step2Done = (stats?.total ?? 0) > 0
  const step3Done = ((stats?.tailored ?? 0) + (stats?.applied ?? 0) + (stats?.interview ?? 0)) > 0
  const doneCount = [step1Done, step2Done, step3Done].filter(Boolean).length

  const checklistSteps = [
    {
      done: step1Done,
      title: 'Set up your profile',
      body: 'Upload your CV and cover letter, then add target roles.',
      to: '/app/profile',
      linkLabel: 'Open Profile →',
    },
    {
      done: step2Done,
      title: 'Search for jobs',
      body: 'Run a search — results save to Applications.',
      to: '/app/jobs',
      linkLabel: 'Search jobs →',
    },
    {
      done: step3Done,
      title: 'Tailor & apply',
      body: 'Tailor documents, then apply on the job site.',
      to: '/app/applications',
      linkLabel: 'Go to Applications →',
    },
  ]

  return (
    <div>
      <h2 className="page-title">Dashboard</h2>
      <p className="page-subtitle">Track your job hunt for {profile.full_name}.</p>

      <div className="checklist-card">
        <div className="checklist-card__head">
          <div>
            <div className="checklist-card__eyebrow">Getting started</div>
            <h3 style={{ margin: 0, fontSize: '1.2rem' }}>Here's how to land your first application</h3>
          </div>
          <span className="checklist-card__count">{doneCount} / 3 done</span>
        </div>
        <div className="checklist-progress">
          <div style={{ width: `${(doneCount / 3) * 100}%` }} />
        </div>
        <div className="checklist-steps">
          {checklistSteps.map((step) => (
            <div key={step.title} className="checklist-step">
              <span className={`checklist-step__badge${step.done ? ' done' : ''}`}>
                {step.done ? '✓' : ''}
              </span>
              <div>
                <strong style={{ fontSize: '0.95rem' }}>{step.title}</strong>
                <p>{step.body}</p>
                <button type="button" className="link-btn" style={{ fontSize: '0.85rem' }} onClick={() => navigate(step.to)}>
                  {step.linkLabel}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {stats && (
        <div className="stats-grid">
          <div className="stat-card"><div className="value">{stats.total}</div><div className="label">Total jobs</div></div>
          <div className="stat-card"><div className="value">{stats.discovered}</div><div className="label">Discovered</div></div>
          <div className="stat-card stat-card--warning"><div className="value">{stats.tailored}</div><div className="label">Tailored</div></div>
          <div className="stat-card stat-card--success"><div className="value">{stats.applied}</div><div className="label">Applied</div></div>
        </div>
      )}

      <div className="quick-grid">
        <button type="button" className="quick-card" onClick={() => navigate('/app/jobs')}>
          <span aria-hidden="true" className="glyph">⌕</span>
          <strong>Search new jobs</strong>
          <span>Find up to 100 matching roles from multiple boards.</span>
        </button>
        <button type="button" className="quick-card" onClick={() => navigate('/app/applications')}>
          <span aria-hidden="true" className="glyph">▤</span>
          <strong>View applications</strong>
          <span>Tailor documents and apply on each job site.</span>
        </button>
        <button type="button" className="quick-card" onClick={() => navigate('/app/profile')}>
          <span aria-hidden="true" className="glyph">☷</span>
          <strong>Update profile</strong>
          <span>Edit target roles, countries, CV, and cover letter.</span>
        </button>
      </div>

      <button
        type="button"
        className="link-btn"
        style={{ marginTop: '1.75rem' }}
        onClick={() => window.dispatchEvent(new CustomEvent('tour:start'))}
      >
        Replay the guided tour
      </button>

      {billing && billing.stripe_configured && !billing.has_stripe_subscription && billing.plan !== 'unlimited' && (
        <div className="card" style={{ marginTop: '1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.8rem', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <span className="badge badge-applied" style={{ textTransform: 'capitalize' }}>{billing.plan}</span>
              {billing.plan === 'trial' && <span className="muted">{billing.trial_days_left} day(s) of trial left</span>}
              <Link to="/app/billing" style={{ fontSize: '0.85rem' }}>Plan & Billing →</Link>
            </div>
            <HelpButton
              className="btn-primary btn-sm"
              onClick={() => navigate('/app/billing')}
              title="Start free trial"
              help="Add your card for a 3-day free trial on Basic. You are only charged when the trial ends."
            >
              Start 3-day free trial
            </HelpButton>
          </div>
        </div>
      )}
    </div>
  )
}
