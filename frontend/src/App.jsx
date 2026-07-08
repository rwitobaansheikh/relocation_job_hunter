import { useEffect, useState } from 'react'
import { NavLink, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { useAuth } from './AuthContext'
import { useTheme } from './ThemeContext'
import { ProfileProvider } from './ProfileContext'
import { JobSearchProvider, useJobSearch } from './JobSearchContext'
import GlobalJobSearchStatus from './components/GlobalJobSearchStatus'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import Profile from './pages/Profile'
import Jobs from './pages/Jobs'
import Applications from './pages/Applications'
import Automation from './pages/Automation'
import Billing from './pages/Billing'
import Settings from './pages/Settings'
import Feedback from './pages/Feedback'
import Admin from './pages/Admin'
import AuthCallback from './pages/AuthCallback'
import HelpButton from './components/HelpButton'
import PlanGate from './components/PlanGate'
import GuidedTour, { TOUR_SEEN_KEY, TOUR_STEPS } from './components/GuidedTour'

function PlanBadge() {
  const [billing, setBilling] = useState(null)
  const refresh = () => {
    api.getBilling().then(setBilling).catch(() => {})
  }
  useEffect(() => {
    refresh()
    const onPlanUpdated = () => refresh()
    window.addEventListener('plan:updated', onPlanUpdated)
    return () => window.removeEventListener('plan:updated', onPlanUpdated)
  }, [])
  if (!billing) return null
  const label = billing.plan === 'unlimited' ? 'Unlimited' : billing.plan
  return (
    <NavLink to="/app/billing" className="plan-badge">
      <span style={{ textTransform: 'capitalize' }}>{label} plan</span>
      {billing.plan === 'trial' && <small>{billing.trial_days_left}d left</small>}
      {billing.plan === 'expired' && <small>upgrade</small>}
    </NavLink>
  )
}

const PRIMARY_NAV = [
  { to: '/app', end: true, label: 'Dashboard', icon: '⌂' },
  { to: '/app/jobs', label: 'Search Jobs', icon: '⌕' },
  { to: '/app/applications', label: 'Applications', icon: '▤' },
  { to: '/app/profile', label: 'Profile', icon: '☷' },
]

const SECONDARY_NAV = [
  { to: '/app/automation', label: 'Automation' },
  { to: '/app/billing', label: 'Plan & Billing' },
  { to: '/app/settings', label: 'Settings' },
  { to: '/app/feedback', label: 'Feedback' },
]

function AppShell({ user, logout }) {
  const { theme, toggleTheme } = useTheme()
  const { searching } = useJobSearch()
  const [navOpen, setNavOpen] = useState(false)
  const [tourStep, setTourStep] = useState(null) // null = inactive

  const closeNav = () => setNavOpen(false)

  useEffect(() => {
    let seen = false
    try {
      seen = localStorage.getItem(TOUR_SEEN_KEY) === '1'
    } catch {
      seen = true
    }
    if (!seen) setTourStep(0)
    const onStart = () => setTourStep(0)
    window.addEventListener('tour:start', onStart)
    return () => window.removeEventListener('tour:start', onStart)
  }, [])

  const endTour = () => {
    try {
      localStorage.setItem(TOUR_SEEN_KEY, '1')
    } catch {
      /* private mode */
    }
    setTourStep(null)
  }

  const tourNext = () => {
    if (tourStep >= TOUR_STEPS.length - 1) endTour()
    else setTourStep(tourStep + 1)
  }

  const tourTarget = tourStep != null ? TOUR_STEPS[tourStep]?.target : null

  const navClass = (to, base) => ({ isActive }) => {
    const classes = []
    if (base) classes.push(base)
    if (isActive) classes.push('active')
    if (tourTarget === to) classes.push('tour-highlight')
    return classes.join(' ') || undefined
  }

  return (
    <div className="layout">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      {/* Mobile top bar */}
      <div className="mobile-topbar">
        <button
          type="button"
          className="icon-btn"
          aria-label="Open menu"
          onClick={() => setNavOpen(true)}
        >
          ☰
        </button>
        <div className="mobile-topbar-brand">
          <img src="/logo-small.png" alt="" />
          <span>jaf<span className="text-accent">low</span></span>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            type="button"
            className="icon-btn"
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            onClick={toggleTheme}
          >
            {theme === 'dark' ? '☀' : '☾'}
          </button>
          <button type="button" className="icon-btn" aria-label="Log out" onClick={logout}>
            ⏻
          </button>
        </div>
      </div>

      {/* Mobile bottom tab bar */}
      <nav aria-label="Primary" className="tabbar">
        {PRIMARY_NAV.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={navClass(item.to)}>
            <span aria-hidden="true" className="nav-icon">{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div
        className={`sidebar-backdrop${navOpen ? ' visible' : ''}`}
        onClick={closeNav}
        aria-hidden="true"
      />

      {/* Desktop sidebar / mobile drawer */}
      <nav aria-label="Main navigation" className={`sidebar${navOpen ? ' sidebar-open' : ''}`}>
        <div className="sidebar-header">
          <h1 style={{ display: 'flex', alignItems: 'center', margin: 0, padding: 0 }}>
            <div className="brand-logo" style={{ fontSize: '1.15rem' }}>
              <img src="/logo-small.png" alt="Logo" />
              <span className="text-main">jobapplication</span><span className="text-accent">flow</span>
            </div>
          </h1>
          <button type="button" className="sidebar-close" aria-label="Close menu" onClick={closeNav}>
            ×
          </button>
        </div>
        {PRIMARY_NAV.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} onClick={closeNav} className={navClass(item.to)}>
            <span aria-hidden="true" className="nav-icon">{item.icon}</span>
            {item.label}
            {item.to === '/app/jobs' && searching && (
              <span className="nav-search-pulse" title="Search in progress" />
            )}
          </NavLink>
        ))}
        <div className="nav-divider" />
        {SECONDARY_NAV.map((item) => (
          <NavLink key={item.to} to={item.to} onClick={closeNav} className={navClass(item.to)}>
            {item.label}
          </NavLink>
        ))}
        {user.role === 'admin' && (
          <NavLink to="/app/admin" onClick={closeNav} className={navClass('/app/admin')}>
            Admin
          </NavLink>
        )}
        <div className="sidebar-footer">
          <HelpButton
            className="btn-secondary theme-toggle"
            style={{ width: '100%' }}
            onClick={toggleTheme}
            title="Theme"
            help="Switch between dark and light mode. Dark mode uses soft accents that are easier on the eyes."
          >
            {theme === 'dark' ? '☀ Light mode' : '☾ Dark mode'}
          </HelpButton>
          <PlanBadge />
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', padding: '0 0.4rem' }}>
            {user.email}
          </div>
          <HelpButton
            className="btn-secondary"
            style={{ width: '100%' }}
            onClick={logout}
            title="Log out"
            help="Sign out of your account on this device. Your data stays saved for next time you log in."
          >
            Log out
          </HelpButton>
        </div>
      </nav>

      <main id="main-content" className="main">
        <div className="page-inner">
          <PlanGate>
            <GlobalJobSearchStatus />
            <Outlet />
          </PlanGate>
        </div>
      </main>

      {tourStep != null && (
        <GuidedTour step={tourStep} onNext={tourNext} onSkip={endTour} />
      )}
    </div>
  )
}

function ProtectedLayout() {
  const { user, loading, logout } = useAuth()

  if (loading) return <div className="layout"><main className="main"><p>Loading...</p></main></div>
  if (!user) return <Navigate to="/login" replace />

  return (
    <ProfileProvider>
      <JobSearchProvider>
        <AppShell user={user} logout={logout} />
      </JobSearchProvider>
    </ProfileProvider>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/app" element={<ProtectedLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="profile" element={<Profile />} />
        <Route path="jobs" element={<Jobs />} />
        <Route path="applications" element={<Applications />} />
        <Route path="automation" element={<Automation />} />
        <Route path="billing" element={<Billing />} />
        <Route path="settings" element={<Settings />} />
        <Route path="feedback" element={<Feedback />} />
        <Route path="admin" element={<Admin />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
