import { createContext, useContext, useEffect, useState } from 'react'
import { api } from './api'

const ProfileContext = createContext(null)

export function ProfileProvider({ children }) {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getProfiles().then((profiles) => {
      if (profiles.length > 0) setProfile(profiles[0])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const refreshProfile = async () => {
    if (profile?.id) {
      const updated = await api.getProfile(profile.id)
      setProfile(updated)
    }
  }

  return (
    <ProfileContext.Provider value={{ profile, setProfile, loading, refreshProfile }}>
      {children}
    </ProfileContext.Provider>
  )
}

export function useProfile() {
  return useContext(ProfileContext)
}
