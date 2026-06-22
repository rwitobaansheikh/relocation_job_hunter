import { useState } from 'react'
import { api } from '../api'

const SOURCE_LABELS = {
  job_posting: 'Job posting',
  website: 'Company website',
  search: 'Web search',
  ai: 'AI ranking',
  ai_discover: 'AI discovery',
  fallback: 'Likely inboxes',
}

export default function RecruitingEmails() {
  const [company, setCompany] = useState('')
  const [website, setWebsite] = useState('')
  const [jobUrl, setJobUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const handleSearch = async (e) => {
    e.preventDefault()
    if (!company.trim() && !website.trim() && !jobUrl.trim()) {
      setError('Enter a company name, website, or job link.')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await api.findRecruitingEmails({
        company: company.trim(),
        website: website.trim(),
        job_url: jobUrl.trim(),
      })
      setResult(data)
    } catch (err) {
      setError(err.message)
    }
    setLoading(false)
  }

  return (
    <div>
      <h2 className="page-title">Recruiting Email Finder</h2>
      <p className="page-subtitle">
        Find 3–6 HR, recruiting, or talent team emails for a company. Paste a job link,
        company website, or company name — no paid APIs required.
      </p>

      <div className="card">
        <form onSubmit={handleSearch}>
          <div className="form-group">
            <label>Company name</label>
            <input
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder="e.g. Acme Corp"
            />
          </div>
          <div className="form-group">
            <label>Company website (optional)</label>
            <input
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              placeholder="e.g. acme.com or https://acme.com/careers"
            />
          </div>
          <div className="form-group">
            <label>Job posting link (optional)</label>
            <input
              value={jobUrl}
              onChange={(e) => setJobUrl(e.target.value)}
              placeholder="https://..."
            />
          </div>
          <p className="muted" style={{ marginBottom: '1rem', fontSize: '0.85rem' }}>
            Provide at least one field. A job link helps extract the employer and scrape the listing.
          </p>
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Searching…' : 'Find recruiting emails'}
          </button>
        </form>
      </div>

      {error && <div className="alert alert-error" style={{ marginTop: '1rem' }}>{error}</div>}

      {result && (
        <div className="card" style={{ marginTop: '1.5rem' }}>
          <h3 style={{ marginBottom: '0.5rem' }}>
            {result.company || 'Results'}
            {result.domain && (
              <span className="muted" style={{ fontWeight: 400, fontSize: '0.9rem' }}>
                {' '}· {result.domain}
              </span>
            )}
          </h3>

          {result.sources_used?.length > 0 && (
            <p className="muted" style={{ fontSize: '0.85rem', marginBottom: '1rem' }}>
              Sources: {result.sources_used.map((s) => SOURCE_LABELS[s] || s).join(', ')}
            </p>
          )}

          {result.message && (
            <div className="alert alert-warning" style={{ marginBottom: '1rem' }}>{result.message}</div>
          )}

          {result.contacts?.length === 0 ? (
            <p className="muted">No contacts found. Try adding the company website or a job link.</p>
          ) : (
            <div className="job-list">
              {result.contacts.map((c, i) => (
                <div key={i} className="job-item" style={{ padding: '0.75rem 0' }}>
                  <div className="job-info">
                    <h3 style={{ fontSize: '1rem' }}>{c.name || c.email}</h3>
                    <div className="meta">
                      <a href={`mailto:${c.email}`}>{c.email}</a>
                      {c.title && ` · ${c.title}`}
                      {c.confidence > 0 && ` · confidence ${c.confidence}%`}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
