import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { useTheme } from '../ThemeContext'

export default function Login() {
  const { user, login } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/app" replace />

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(form.email, form.password)
      navigate('/app')
    } catch (err) {
      setError(err.message)
    }
    setBusy(false)
  }

  return (
    <div className="auth-wrap">
      <button type="button" className="btn-secondary theme-toggle-auth" onClick={toggleTheme}>
        {theme === 'dark' ? '☀ Light mode' : '☾ Dark mode'}
      </button>
      <div className="auth-card card">
        <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          <img src="/logo-full.png" alt="Job Application Flow" style={{ height: '36px', objectFit: 'contain' }} />
        </div>
        <h2 style={{ fontSize: '1.5rem' }}>Welcome back</h2>
        <p className="page-subtitle" style={{ textAlign: 'center', marginBottom: '1.5rem' }}>Log in to continue</p>
        {error && <div className="alert alert-error">{error}</div>}
        <form onSubmit={submit}>
          <div className="form-group">
            <label>Email</label>
            <input name="email" type="email" value={form.email} onChange={handleChange} required />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input name="password" type="password" value={form.password} onChange={handleChange} required />
          </div>
          <button className="btn-primary" style={{ width: '100%' }} disabled={busy}>
            {busy ? 'Logging in...' : 'Log in'}
          </button>
        </form>
        <div className="auth-switch">
          Don't have an account? <Link to="/register">Sign up</Link>
        </div>
      </div>
    </div>
  )
}
