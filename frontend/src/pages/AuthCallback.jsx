import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { redirectToTrialCheckoutIfNeeded } from '../utils/trialCheckout'

export default function AuthCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { loginWithToken } = useAuth()
  const [error, setError] = useState(null)

  useEffect(() => {
    const errorParam = searchParams.get('error')
    if (errorParam) {
      setError(errorParam)
      return
    }

    const token = searchParams.get('token')
    if (!token) {
      navigate('/login', { replace: true })
      return
    }

    loginWithToken(token)
      .then(async () => {
        const redirected = await redirectToTrialCheckoutIfNeeded()
        if (!redirected) navigate('/app', { replace: true })
      })
      .catch((err) => setError(err.message || 'Login failed'))
  }, [searchParams, navigate, loginWithToken])

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', flexDirection: 'column', gap: '1rem', background: 'var(--bg-gradient)' }}>
      <div className="brand-logo" style={{ fontSize: '1.75rem' }}>
        <img src="/logo-small.png" alt="Logo" />
        <span className="text-main">jobapplication</span><span className="text-accent">flow</span>
      </div>
      {error ? (
        <>
          <div className="alert alert-error" style={{ maxWidth: '28rem', textAlign: 'center' }}>{error}</div>
          <Link to="/login" className="btn-secondary">Back to login</Link>
        </>
      ) : (
        <p style={{ color: 'var(--text-muted)' }}>Completing login...</p>
      )}
    </div>
  )
}
