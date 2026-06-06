import { useState } from 'react'
import { api } from '../api'
import { useProfile } from '../ProfileContext'

export default function Jobs() {
  const { profile } = useProfile()
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)

  const handleSearch = async () => {
    if (!profile?.id) {
      setError('Create a profile first')
      return
    }
    if (!profile.cv_path) {
      setError('Upload your CV before searching')
      return
    }

    setSearching(true)
    setError(null)
    setResults(null)
    try {
      const stats = await api.searchJobs(profile.id, 100)
      setResults(stats)
    } catch (err) {
      setError(err.message)
    }
    setSearching(false)
  }

  if (!profile) {
    return <div className="empty-state"><p>Create your profile first to search for jobs.</p></div>
  }

  return (
    <div>
      <h2 className="page-title">Search Jobs</h2>
      <p className="page-subtitle">
        Find up to 100 graduate/junior/intern roles posted in the last 48 hours
      </p>

      <div className="card" style={{ marginBottom: '2rem' }}>
        <h3 style={{ marginBottom: '0.8rem' }}>Search Criteria</h3>
        <ul style={{ color: 'var(--text-muted)', fontSize: '0.9rem', paddingLeft: '1.2rem', marginBottom: '1rem' }}>
          <li>Experience: graduate, junior, or intern</li>
          <li>Posted within the last 48 hours</li>
          <li>Relocation/visa support is preferred (boosts ranking) but not required</li>
          <li>Ranked by relevance to your CV and target roles</li>
          <li>Sources: LinkedIn, RemoteOK, Remotive, We Work Remotely, Relocate.me</li>
        </ul>
        <button className="btn-primary" onClick={handleSearch} disabled={searching}>
          {searching ? 'Searching... (this may take a minute)' : 'Start Job Search'}
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {results && (
        <div className="card">
          <h3 style={{ marginBottom: '1rem' }}>Search Results</h3>
          <div className="stats-grid">
            <div className="stat-card"><div className="value">{results.jobs_found}</div><div className="label">Total Found</div></div>
            <div className="stat-card"><div className="value">{results.jobs_filtered_excluded}</div><div className="label">US / Excluded</div></div>
            <div className="stat-card"><div className="value">{results.jobs_filtered_age}</div><div className="label">Filtered (Age)</div></div>
            <div className="stat-card"><div className="value">{results.jobs_filtered_experience}</div><div className="label">Wrong Level</div></div>
            <div className="stat-card"><div className="value">{results.jobs_filtered_role}</div><div className="label">Off-Role</div></div>
            <div className="stat-card"><div className="value">{results.jobs_filtered_country}</div><div className="label">Off-Country</div></div>
            <div className="stat-card"><div className="value">{results.jobs_stored}</div><div className="label">New Jobs Saved</div></div>
          </div>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            View saved jobs in the <a href="/applications">Applications</a> page to tailor documents and send outreach.
          </p>
        </div>
      )}
    </div>
  )
}
