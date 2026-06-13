import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { useTheme } from '../ThemeContext'

export default function Register() {
  const { user, register } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const [form, setForm] = useState({ full_name: '', email: '', password: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/app" replace />

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    if (form.password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await register(form)
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
        <div style={{ textAlign: 'center', marginBottom: '2rem', display: 'flex', justifyContent: 'center' }}>
          <div className="brand-logo" style={{ fontSize: '1.75rem' }}>
            <img src="/logo-small.png" alt="Logo" />
            <span className="text-main">jobapplication</span><span className="text-accent">flow</span>
          </div>
        </div>
        <h2 style={{ fontSize: '1.5rem', textAlign: 'center' }}>Create your account</h2>
        <p className="page-subtitle" style={{ textAlign: 'center', marginBottom: '1.5rem' }}>Start your automated job search</p>
        {error && <div className="alert alert-error">{error}</div>}
        <form onSubmit={submit}>
          <div className="form-group">
            <label>Full Name</label>
            <input name="full_name" value={form.full_name} onChange={handleChange} required />
          </div>
          <div className="form-group">
            <label>Email</label>
            <input name="email" type="email" value={form.email} onChange={handleChange} required />
          </div>
          <div className="form-group">
            <label>Password (min 8 characters)</label>
            <input name="password" type="password" value={form.password} onChange={handleChange} required />
          </div>
          <button className="btn-primary" style={{ width: '100%' }} disabled={busy}>
            {busy ? 'Creating account...' : 'Sign up'}
          </button>
        </form>
        <div className="auth-switch">
          Already have an account? <Link to="/login">Log in</Link>
        </div>
      </div>
    </div>
  )
}
