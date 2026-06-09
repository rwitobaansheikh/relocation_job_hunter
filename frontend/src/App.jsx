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

  if (loading) return <div className="layout"><main className="main"><p>Loading...</p></main></div>
  if (!user) return <Navigate to="/login" replace />

  return (
    <ProfileProvider>
      <div className="layout">
        <nav className="sidebar">
          <h1>Job Application Flow</h1>
          <NavLink to="/app" end>Dashboard</NavLink>
          <NavLink to="/app/profile">Profile & Uploads</NavLink>
          <NavLink to="/app/jobs">Search Jobs</NavLink>
          <NavLink to="/app/applications">Applications</NavLink>
          <NavLink to="/app/automation">Automation</NavLink>
          <NavLink to="/app/billing">Plan & Billing</NavLink>
          <NavLink to="/app/settings">Settings</NavLink>
          <NavLink to="/app/feedback">Feedback</NavLink>
          {user.role === 'admin' && <NavLink to="/app/admin">Admin</NavLink>}
          <div style={{ marginTop: 'auto', paddingTop: '1rem' }}>
            <button
              type="button"
              className="btn-secondary theme-toggle"
              style={{ width: '100%', marginBottom: '0.5rem' }}
              onClick={toggleTheme}
            >
              {theme === 'dark' ? '☀ Light mode' : '☾ Dark mode'}
            </button>
            <PlanBadge />
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.4rem 0' }}>
              {user.email}
            </div>
            <button className="btn-secondary" style={{ width: '100%' }} onClick={logout}>
              Log out
            </button>
          </div>
        </nav>
        <main className="main">
          <Outlet />
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
