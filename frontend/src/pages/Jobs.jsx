import { useEffect, useState } from 'react'
import { api } from '../api'
import SearchCriteriaPanel, { SEARCH_CRITERIA_KEY } from '../components/SearchCriteriaPanel'
import HelpButton from '../components/HelpButton'
import { POSTED_OPTIONS, SENIORITY_OPTIONS, WORK_TYPE_OPTIONS } from '../constants/search'
import { useProfile } from '../ProfileContext'
import { useJobSearch } from '../JobSearchContext'

export default function Jobs() {
  const { profile } = useProfile()
  const {
    searching,
    startSearch,
    results,
    error: searchError,
    statusMessage,
  } = useJobSearch()
  const [error, setError] = useState(null)
  const [criteriaMsg, setCriteriaMsg] = useState(null)

  const [seniority, setSeniority] = useState([])
  const [workTypes, setWorkTypes] = useState([])
  const [postedWithin, setPostedWithin] = useState(48)
  const [minSalary, setMinSalary] = useState('')
  const [maxSalary, setMaxSalary] = useState('')
  const [locations, setLocations] = useState('')
  const [searchRoles, setSearchRoles] = useState([])

  const [criteria, setCriteria] = useState(null)
  const [selectedRoles, setSelectedRoles] = useState(new Set())
  const [selectedLocations, setSelectedLocations] = useState(new Set())
  const [selectedSeniority, setSelectedSeniority] = useState(new Set())
  const [suggesting, setSuggesting] = useState(false)
  const [showCriteria, setShowCriteria] = useState(false)

  useEffect(() => {
    const raw = sessionStorage.getItem(SEARCH_CRITERIA_KEY)
    if (!raw) return
    try {
      const c = JSON.parse(raw)
      if (c.seniority_levels?.length) setSeniority(c.seniority_levels)
      if (c.posted_within_hours) setPostedWithin(String(c.posted_within_hours))
      if (c.locations?.length) setLocations(c.locations.join(', '))
      if (c.roles?.length) setSearchRoles(c.roles)
      if (c.min_salary != null) setMinSalary(String(c.min_salary))
      if (c.max_salary != null) setMaxSalary(String(c.max_salary))
      setCriteriaMsg({ type: 'success', text: 'Applied suggested search criteria from your profile.' })
      sessionStorage.removeItem(SEARCH_CRITERIA_KEY)
    } catch {
      sessionStorage.removeItem(SEARCH_CRITERIA_KEY)
    }
  }, [])

  const [importUrl, setImportUrl] = useState('')
  const [importing, setImporting] = useState(false)
  const [importMsg, setImportMsg] = useState(null)
  const [addingJob, setAddingJob] = useState(false)
  const [jobForm, setJobForm] = useState(null)

  const emptyForm = (url = '') => ({
    url,
    title: '',
    company: '',
    company_domain: '',
    location: '',
    description: '',
    seniority_level: '',
    salary_min: '',
    salary_max: '',
    salary_currency: '',
    salary_text: '',
    posted_at: '',
  })

  const setField = (key, value) => setJobForm((prev) => ({ ...prev, [key]: value }))

  const handleFetch = async () => {
    const url = importUrl.trim()
    if (!url) {
      setImportMsg({ type: 'error', text: 'Paste a job link first' })
      return
    }
    setImporting(true)
    setImportMsg(null)
    try {
      const data = await api.importJob(url)
      setJobForm({
        ...emptyForm(data.url || url),
        title: data.title || '',
        company: data.company || '',
        company_domain: data.company_domain || '',
        location: data.location || '',
        description: data.description || '',
        salary_min: data.salary_min ?? '',
        salary_max: data.salary_max ?? '',
        salary_currency: data.salary_currency || '',
        salary_text: data.salary_text || '',
        posted_at: data.posted_at ? data.posted_at.slice(0, 10) : '',
      })
      setImportMsg({ type: data.scraped ? 'info' : 'error', text: data.message || 'Fetched.' })
    } catch (err) {
      setJobForm(emptyForm(url))
      setImportMsg({ type: 'error', text: `Import failed: ${err.message}. Enter details manually.` })
    }
    setImporting(false)
  }

  const handleManualEntry = () => {
    setImportMsg(null)
    setJobForm(emptyForm(importUrl.trim()))
  }

  const handleAddJob = async () => {
    if (!jobForm?.title.trim() || !jobForm?.company.trim()) {
      setImportMsg({ type: 'error', text: 'Title and company are required' })
      return
    }
    if (!jobForm?.url.trim()) {
      setImportMsg({ type: 'error', text: 'A job link/URL is required' })
      return
    }
    setAddingJob(true)
    setImportMsg(null)
    try {
      const payload = {
        url: jobForm.url.trim(),
        title: jobForm.title.trim(),
        company: jobForm.company.trim(),
        company_domain: jobForm.company_domain.trim(),
        location: jobForm.location.trim(),
        description: jobForm.description,
        seniority_level: jobForm.seniority_level || '',
        salary_currency: jobForm.salary_currency || '',
        salary_text: jobForm.salary_text || '',
      }
      if (jobForm.salary_min !== '') payload.salary_min = Number(jobForm.salary_min)
      if (jobForm.salary_max !== '') payload.salary_max = Number(jobForm.salary_max)
      if (jobForm.posted_at) payload.posted_at = jobForm.posted_at
      await api.addManualJob(payload)
      setImportMsg({ type: 'success', text: 'Job added to your applications.' })
      setJobForm(null)
      setImportUrl('')
    } catch (err) {
      setImportMsg({ type: 'error', text: err.message })
    }
    setAddingJob(false)
  }

  const toggleLevel = (value) => {
    setSeniority((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value]
    )
  }

  const toggleWorkType = (value) => {
    setWorkTypes((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value]
    )
  }

  const initSelection = (data) => {
    setSelectedRoles(new Set(data.roles || []))
    setSelectedLocations(new Set(data.locations || []))
    setSelectedSeniority(new Set(data.seniority_levels || []))
  }

  const suggestCriteria = async () => {
    setSuggesting(true)
    setCriteriaMsg(null)
    setShowCriteria(true)
    try {
      const res = await api.suggestSearchCriteria()
      if (!res.roles?.length) {
        setCriteriaMsg({ type: 'error', text: res.message || 'No criteria suggested' })
        setCriteria(null)
      } else {
        setCriteria(res)
        initSelection(res)
        setCriteriaMsg({ type: 'success', text: 'Suggested criteria loaded — apply to filters below.' })
      }
    } catch (err) {
      setCriteriaMsg({ type: 'error', text: err.message })
    }
    setSuggesting(false)
  }

  const toggle = (setter, value) => {
    setter((prev) => {
      const next = new Set(prev)
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return next
    })
  }

  const applyCriteriaToFilters = () => {
    if (!criteria) return
    const roles = criteria.roles.filter((r) => selectedRoles.has(r))
    const locs = criteria.locations.filter((l) => selectedLocations.has(l))
    const levels = criteria.seniority_levels.filter((s) => selectedSeniority.has(s))
    setSearchRoles(roles)
    setLocations(locs.length > 0 ? locs[0] : '')
    if (levels.length) setSeniority(levels)
    if (criteria.posted_within_hours) setPostedWithin(String(criteria.posted_within_hours))
    setMinSalary(criteria.min_salary != null ? String(criteria.min_salary) : '')
    setMaxSalary(criteria.max_salary != null ? String(criteria.max_salary) : '')
    setCriteriaMsg({ type: 'success', text: 'Filters updated from suggestions. Click Start Job Search when ready.' })
  }

  useEffect(() => {
    if (statusMessage) setCriteriaMsg(statusMessage)
  }, [statusMessage])

  useEffect(() => {
    if (searchError) setError(searchError)
  }, [searchError])

  const handleSearch = () => {
    if (!profile?.cv_path) {
      setError('Upload your CV before searching')
      return
    }
    setError(null)
    startSearch({
      seniority,
      workTypes,
      postedWithin,
      locations,
      searchRoles,
      minSalary,
      maxSalary,
    })
  }

  const canSuggest = profile?.cv_path && profile?.baseline_cover_letter_path

  if (!profile) {
    return <div className="empty-state"><p>Create your profile first to search for jobs.</p></div>
  }

  return (
    <div>
      <h2 className="page-title">Search Jobs</h2>
      <p className="page-subtitle">
        Set your filters and search for matching roles — results save to Applications automatically.
      </p>

      <div className="card" style={{ marginBottom: '2rem' }}>
        <h3 style={{ marginBottom: '0.5rem' }}>Add a job by link</h3>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '0.8rem' }}>
          Paste a job posting URL. We'll try to read the details automatically; if a
          site blocks scraping, you can fill them in yourself.
        </p>
        <div className="filter-grid" style={{ gridTemplateColumns: '1fr auto auto', alignItems: 'end' }}>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label>Job link</label>
            <input
              type="text"
              placeholder="https://company.com/careers/123"
              value={importUrl}
              onChange={(e) => setImportUrl(e.target.value)}
            />
          </div>
          <HelpButton
            className="btn-primary"
            onClick={handleFetch}
            disabled={importing}
            title="Fetch details"
            help="Reads the job posting URL and fills in title, company, location, and description automatically when the site allows it."
          >
            {importing ? 'Fetching…' : 'Fetch details'}
          </HelpButton>
          <HelpButton
            className="btn-secondary"
            onClick={handleManualEntry}
            disabled={importing}
            title="Enter manually"
            help="Skip automatic scraping and type the job details yourself — useful when a site blocks our reader."
          >
            Enter manually
          </HelpButton>
        </div>

        {importMsg && (
          <div className={`alert alert-${importMsg.type}`} style={{ marginTop: '1rem', marginBottom: 0 }}>
            {importMsg.text}
          </div>
        )}

        {jobForm && (
          <div style={{ marginTop: '1.2rem', borderTop: '1px solid var(--border)', paddingTop: '1.2rem' }}>
            <div className="filter-grid">
              <div className="form-group">
                <label>Job title *</label>
                <input type="text" value={jobForm.title} onChange={(e) => setField('title', e.target.value)} />
              </div>
              <div className="form-group">
                <label>Company *</label>
                <input type="text" value={jobForm.company} onChange={(e) => setField('company', e.target.value)} />
              </div>
              <div className="form-group">
                <label>Location</label>
                <input type="text" value={jobForm.location} onChange={(e) => setField('location', e.target.value)} />
              </div>
              <div className="form-group">
                <label>Company domain (for contacts)</label>
                <input type="text" placeholder="company.com" value={jobForm.company_domain} onChange={(e) => setField('company_domain', e.target.value)} />
              </div>
              <div className="form-group">
                <label>Seniority</label>
                <select value={jobForm.seniority_level} onChange={(e) => setField('seniority_level', e.target.value)}>
                  <option value="">Auto-detect</option>
                  {SENIORITY_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Posted date</label>
                <input type="date" value={jobForm.posted_at} onChange={(e) => setField('posted_at', e.target.value)} />
              </div>
              <div className="form-group">
                <label>Salary min</label>
                <input type="number" min="0" step="1000" value={jobForm.salary_min} onChange={(e) => setField('salary_min', e.target.value)} />
              </div>
              <div className="form-group">
                <label>Salary max</label>
                <input type="number" min="0" step="1000" value={jobForm.salary_max} onChange={(e) => setField('salary_max', e.target.value)} />
              </div>
              <div className="form-group">
                <label>Job link</label>
                <input type="text" value={jobForm.url} onChange={(e) => setField('url', e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label>Job description</label>
              <textarea
                rows={8}
                placeholder="Paste the full job description here"
                value={jobForm.description}
                onChange={(e) => setField('description', e.target.value)}
              />
            </div>
            <div style={{ display: 'flex', gap: '0.6rem' }}>
              <HelpButton
                className="btn-primary"
                onClick={handleAddJob}
                disabled={addingJob}
                title="Add Job"
                help="Saves this job to your Applications list so you can tailor documents and apply on the job site."
              >
                {addingJob ? 'Adding…' : 'Add Job'}
              </HelpButton>
              <HelpButton
                className="btn-secondary"
                onClick={() => { setJobForm(null); setImportMsg(null) }}
                disabled={addingJob}
                title="Cancel"
                help="Discard the form without saving this job."
              >
                Cancel
              </HelpButton>
            </div>
          </div>
        )}
      </div>

      <div className="card" style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0 }}>Filters</h3>
          {canSuggest && (
            <HelpButton
              type="button"
              className="btn-secondary"
              onClick={suggestCriteria}
              disabled={suggesting}
              title="Suggest criteria from CV"
              help="AI reads your CV and cover letter to recommend roles, locations, seniority levels, and salary filters tailored to you."
            >
              {suggesting ? 'Analyzing…' : 'Suggest criteria from CV'}
            </HelpButton>
          )}
        </div>

        {criteriaMsg && <div className={`alert alert-${criteriaMsg.type}`} style={{ marginBottom: '1rem' }}>{criteriaMsg.text}</div>}

        {showCriteria && criteria && (
          <div className="role-suggest-box" style={{ marginBottom: '1rem' }}>
            <SearchCriteriaPanel
              criteria={criteria}
              selectedRoles={selectedRoles}
              selectedLocations={selectedLocations}
              selectedSeniority={selectedSeniority}
              onToggleRole={(r) => toggle(setSelectedRoles, r)}
              onToggleLocation={(l) => toggle(setSelectedLocations, l)}
              onToggleSeniority={(s) => toggle(setSelectedSeniority, s)}
              onApplySearch={applyCriteriaToFilters}
              applySearchLabel="Apply to filters"
            />
          </div>
        )}

        {searchRoles.length > 0 && (
          <p className="muted" style={{ fontSize: '0.85rem', marginBottom: '1rem' }}>
            Searching roles: <strong>{searchRoles.join(', ')}</strong>
          </p>
        )}

        {(locations.trim() || profile?.target_countries) && (
          <p className="muted" style={{ fontSize: '0.85rem', marginBottom: '1rem' }}>
            Locations:{' '}
            <strong>{locations.trim() ? locations : profile.target_countries}</strong>
          </p>
        )}

        <div className="form-group">
          <label>Work type</label>
          <div className="checkbox-row">
            {WORK_TYPE_OPTIONS.map((opt) => (
              <label key={opt.value} className="checkbox-pill">
                <input
                  type="checkbox"
                  checked={workTypes.includes(opt.value)}
                  onChange={() => toggleWorkType(opt.value)}
                />
                {opt.label}
              </label>
            ))}
          </div>
        </div>

        <div className="form-group">
          <label>Seniority level</label>
          <div className="checkbox-row">
            {SENIORITY_OPTIONS.map((opt) => (
              <label key={opt.value} className="checkbox-pill">
                <input
                  type="checkbox"
                  checked={seniority.includes(opt.value)}
                  onChange={() => toggleLevel(opt.value)}
                />
                {opt.label}
              </label>
            ))}
          </div>
        </div>

        <div className="filter-grid">
          <div className="form-group">
            <label>Posted within</label>
            <select value={postedWithin} onChange={(e) => setPostedWithin(e.target.value)}>
              {POSTED_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Min salary (annual)</label>
            <input
              type="number"
              min="0"
              step="1000"
              placeholder="e.g. 40000"
              value={minSalary}
              onChange={(e) => setMinSalary(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label>Max salary (annual)</label>
            <input
              type="number"
              min="0"
              step="1000"
              placeholder="optional"
              value={maxSalary}
              onChange={(e) => setMaxSalary(e.target.value)}
            />
          </div>
        </div>

        <div className="form-group">
          <label>Location (single country/city)</label>
          <input
            type="text"
            placeholder="e.g. Netherlands — blank uses your profile countries"
            value={locations}
            onChange={(e) => setLocations(e.target.value.replace(/,/g, ''))}
          />
        </div>

        <HelpButton
          className="btn-primary"
          onClick={handleSearch}
          disabled={searching}
          title="Start Job Search"
          help="Runs a search across LinkedIn and other boards. Progress stays visible if you switch pages — you can stop it anytime."
        >
          {searching ? 'Searching…' : 'Start Job Search'}
        </HelpButton>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {results && !searching && (
        <div className="card">
          <p style={{ fontSize: '1.05rem', marginBottom: '0.6rem' }}>
            Found <strong>{results.jobs_found}</strong> matching {results.jobs_found === 1 ? 'job' : 'jobs'}.
            {' '}
            <strong>{results.jobs_stored}</strong> {results.jobs_stored === 1 ? 'was' : 'were'} saved to{' '}
            <a href="/app/applications">Applications</a>.
          </p>
        </div>
      )}
    </div>
  )
}
