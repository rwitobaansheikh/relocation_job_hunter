import { useEffect, useState } from 'react'
import { api } from '../api'

export function useOAuthProviders() {
  const [providers, setProviders] = useState({ google: false, linkedin: false, loaded: false })

  useEffect(() => {
    let cancelled = false
    api.getOAuthStatus()
      .then((status) => {
        if (!cancelled) {
          setProviders({
            google: Boolean(status.google),
            linkedin: Boolean(status.linkedin),
            loaded: true,
          })
        }
      })
      .catch(() => {
        if (!cancelled) setProviders({ google: false, linkedin: false, loaded: true })
      })
    return () => { cancelled = true }
  }, [])

  return providers
}
