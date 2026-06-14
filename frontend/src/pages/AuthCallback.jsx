import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../AuthContext'

export default function AuthCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { loginWithToken } = useAuth()
  const [error, setError] = useState(null)
  
  useEffect(() => {
    const token = searchParams.get('token')
    if (token) {
      loginWithToken(token)
        .then(() => {
          navigate('/app', { replace: true })
        })
        .catch((err) => {
          setError(err.message || 'Login failed')
        })
    } else {
      navigate('/login', { replace: true })
    }
  }, [searchParams, navigate, loginWithToken])

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', flexDirection: 'column', gap: '1rem', background: 'var(--bg-gradient)' }}>
      <div className="brand-logo" style={{ fontSize: '1.75rem' }}>
        <img src="/logo-small.png" alt="Logo" />
        <span className="text-main">jobapplication</span><span className="text-accent">flow</span>
      </div>
      {error ? (
        <div className="alert alert-error">{error}</div>
      ) : (
        <p style={{ color: 'var(--text-muted)' }}>Completing login...</p>
      )}
    </div>
  )
}