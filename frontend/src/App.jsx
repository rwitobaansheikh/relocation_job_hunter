import { useEffect, useState } from 'react'
import { NavLink, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { useAuth } from './AuthContext'
import { useTheme } from './ThemeContext'
import { ProfileProvider } from './ProfileContext'
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

function PlanBadge() {
  const [billing, setBilling] = useState(null)
  useEffect(() => {
    api.getBilling().then(setBilling).catch(() => {})
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

function ProtectedLayout() {
  const { user, loading, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const [navOpen, setNavOpen] = useState(false)

  const closeNav = () => setNavOpen(false)

  if (loading) return <div className="layout"><main className="main"><p>Loading...</p></main></div>
  if (!user) return <Navigate to="/login" replace />

  return (
    <ProfileProvider>
      <div className="layout">
        <button
          type="button"
          className="mobile-nav-toggle"
          aria-label="Open navigation menu"
          onClick={() => setNavOpen(true)}
        >
          ☰
        </button>
        <div
          className={`sidebar-backdrop${navOpen ? ' visible' : ''}`}
          onClick={closeNav}
          aria-hidden="true"
        />
        <nav className={`sidebar${navOpen ? ' sidebar-open' : ''}`}>
          <div className="sidebar-header">
            <h1 style={{ display: 'flex', alignItems: 'center', margin: 0, padding: 0 }}>
              <div className="brand-logo" style={{ fontSize: '1.25rem' }}>
                <img src="/logo-small.png" alt="Logo" />
                <span className="text-main">jobapplication</span><span className="text-accent">flow</span>
              </div>
            </h1>
            <button type="button" className="sidebar-close" aria-label="Close menu" onClick={closeNav}>
              ×
            </button>
          </div>
          <NavLink to="/app" end onClick={closeNav}>Dashboard</NavLink>
          <NavLink to="/app/profile" onClick={closeNav}>Profile & Uploads</NavLink>
          <NavLink to="/app/jobs" onClick={closeNav}>Search Jobs</NavLink>
          <NavLink to="/app/applications" onClick={closeNav}>Applications</NavLink>
          <NavLink to="/app/automation" onClick={closeNav}>Automation</NavLink>
          <NavLink to="/app/billing" onClick={closeNav}>Plan & Billing</NavLink>
          <NavLink to="/app/settings" onClick={closeNav}>Settings</NavLink>
          <NavLink to="/app/feedback" onClick={closeNav}>Feedback</NavLink>
          {user.role === 'admin' && <NavLink to="/app/admin" onClick={closeNav}>Admin</NavLink>}
          <div style={{ marginTop: 'auto', paddingTop: '1rem' }}>
            <HelpButton
              className="btn-secondary theme-toggle"
              style={{ width: '100%', marginBottom: '0.5rem' }}
              onClick={toggleTheme}
              title="Theme"
              help="Switch between dark and light mode. Dark mode uses soft pastel accents that are easier on the eyes."
            >
              {theme === 'dark' ? '☀ Light mode' : '☾ Dark mode'}
            </HelpButton>
            <PlanBadge />
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.4rem 0' }}>
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
        <main className="main">
          <PlanGate>
            <Outlet />
          </PlanGate>
        </main>
      </div>
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
