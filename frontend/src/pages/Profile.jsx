import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import SearchCriteriaPanel, { saveSearchCriteriaForJobs } from '../components/SearchCriteriaPanel'
import HelpButton from '../components/HelpButton'
import { useProfile } from '../ProfileContext'

function parseCsv(csv) {
  return csv.split(',').map((r) => r.trim()).filter(Boolean)
}

function joinCsv(items) {
  return items.join(', ')
}

function mergeUnique(existing, picked) {
  const merged = [...existing]
  const seen = new Set(existing.map((x) => x.toLowerCase()))
  for (const item of picked) {
    if (!seen.has(item.toLowerCase())) {
      merged.push(item)
      seen.add(item.toLowerCase())
    }
  }
  return merged
}

export default function Profile() {
  const navigate = useNavigate()
  const { profile, setProfile, refreshProfile } = useProfile()
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    phone: '',
    location: '',
    linkedin_url: '',
    skills: '',
    summary: '',
    target_roles: '',
    target_countries: '',
  })
  const [message, setMessage] = useState(null)
  const [saving, setSaving] = useState(false)
  const [criteria, setCriteria] = useState(null)
  const [selectedRoles, setSelectedRoles] = useState(new Set())
  const [selectedLocations, setSelectedLocations] = useState(new Set())
  const [selectedSeniority, setSelectedSeniority] = useState(new Set())
  const [suggesting, setSuggesting] = useState(false)
  const [showCriteria, setShowCriteria] = useState(false)

  useEffect(() => {
    if (profile) {
      setForm({
        full_name: profile.full_name || '',
        email: profile.email || '',
        phone: profile.phone || '',
        location: profile.location || '',
        linkedin_url: profile.linkedin_url || '',
        skills: profile.skills || '',
        summary: profile.summary || '',
        target_roles: profile.target_roles || '',
        target_countries: profile.target_countries || '',
      })
    }
  }, [profile])

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value })

  const handleSave = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const updated = await api.updateProfile(form)
      setProfile(updated)
      setMessage({ type: 'success', text: 'Profile saved successfully' })
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
    setSaving(false)
  }

  const initSelection = (data) => {
    setSelectedRoles(new Set(data.roles || []))
    setSelectedLocations(new Set(data.locations || []))
    setSelectedSeniority(new Set(data.seniority_levels || []))
  }

  const viewSuggestedCriteria = async () => {
    setSuggesting(true)
    setMessage(null)
    setShowCriteria(true)
    try {
      const res = await api.suggestSearchCriteria()
      if (!res.roles?.length) {
        setMessage({ type: 'error', text: res.message || 'No criteria suggested' })
        setCriteria(null)
      } else {
        setCriteria(res)
        initSelection(res)
        setMessage({
          type: 'success',
          text: 'Review the suggested search criteria below. Apply to your profile or jump to job search.',
        })
      }
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
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

  const pickedRoles = () => criteria.roles.filter((r) => selectedRoles.has(r))
  const pickedLocations = () => criteria.locations.filter((l) => selectedLocations.has(l))

  const applyToProfile = async () => {
    if (!criteria) return
    const roles = pickedRoles()
    const locations = pickedLocations()
    const payload = {
      ...form,
      target_roles: joinCsv(mergeUnique(parseCsv(form.target_roles), roles)),
      target_countries: joinCsv(mergeUnique(parseCsv(form.target_countries), locations)),
    }
    setSaving(true)
    try {
      const updated = await api.updateProfile(payload)
      setForm((f) => ({
        ...f,
        target_roles: updated.target_roles || payload.target_roles,
        target_countries: updated.target_countries || payload.target_countries,
      }))
      setProfile(updated)
      setMessage({ type: 'success', text: 'Suggested roles and locations saved to your profile.' })
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
    setSaving(false)
  }

  const useForJobSearch = () => {
    if (!criteria) return
    saveSearchCriteriaForJobs(criteria, {
      roles: selectedRoles,
      locations: selectedLocations,
      seniority: selectedSeniority,
    })
    navigate('/app/jobs')
  }

  const handleFileUpload = async (type, file) => {
    setMessage(null)
    try {
      if (type === 'cv') await api.uploadCV(file)
      else await api.uploadCoverLetter(file)
      await refreshProfile()
      setMessage({ type: 'success', text: `${type === 'cv' ? 'CV' : 'Cover letter'} uploaded successfully` })
      setCriteria(null)
      setShowCriteria(false)
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
  }

  const hasCv = Boolean(profile?.cv_path)
  const hasCover = Boolean(profile?.baseline_cover_letter_path)
  const canSuggest = hasCv && hasCover

  return (
    <div>
      <h2 className="page-title">Profile & Uploads</h2>
      <p className="page-subtitle">Set up your details, upload your CV and baseline cover letter</p>

      {message && <div className={`alert alert-${message.type}`}>{message.text}</div>}

      <div className="grid-2">
        <div className="card">
          <h3 style={{ marginBottom: '1rem' }}>Personal Details</h3>
          <div className="form-group">
            <label>Full Name</label>
            <input name="full_name" value={form.full_name} onChange={handleChange} />
          </div>
          <div className="form-group">
            <label>Email</label>
            <input name="email" type="email" value={form.email} onChange={handleChange} />
          </div>
          <div className="form-group">
            <label>Phone</label>
            <input name="phone" value={form.phone} onChange={handleChange} />
          </div>
          <div className="form-group">
            <label>Current Location</label>
            <input name="location" value={form.location} onChange={handleChange} placeholder="e.g. London, UK" />
          </div>
          <div className="form-group">
            <label>LinkedIn URL</label>
            <input name="linkedin_url" value={form.linkedin_url} onChange={handleChange} />
          </div>
          <div className="form-group">
            <label>Skills (comma-separated)</label>
            <input name="skills" value={form.skills} onChange={handleChange} placeholder="Python, React, FastAPI" />
          </div>

          <div className="form-group">
            <label>Target Roles (comma-separated)</label>
            <input
              name="target_roles"
              value={form.target_roles}
              onChange={handleChange}
              placeholder="Software Engineer, Backend Developer"
            />
          </div>

          <div className="form-group">
            <label>Target Countries / Locations (comma-separated)</label>
            <input name="target_countries" value={form.target_countries} onChange={handleChange} placeholder="Remote, Germany, United Kingdom" />
          </div>

          {canSuggest && (
            <div className="role-suggest-box">
              <HelpButton
                type="button"
                className="btn-secondary"
                onClick={viewSuggestedCriteria}
                disabled={suggesting}
                title="View suggested search criteria"
                help="AI analyzes your CV and cover letter to recommend target roles, countries, seniority, and filters you can apply to your profile or job search."
              >
                {suggesting ? 'Analyzing documents…' : 'View suggested search criteria'}
              </HelpButton>
              <p className="muted" style={{ marginTop: '0.5rem', fontSize: '0.82rem' }}>
                AI recommends roles, locations, seniority and filters tuned for maximum relevant results.
              </p>
              {showCriteria && criteria && (
                <SearchCriteriaPanel
                  criteria={criteria}
                  selectedRoles={selectedRoles}
                  selectedLocations={selectedLocations}
                  selectedSeniority={selectedSeniority}
                  onToggleRole={(r) => toggle(setSelectedRoles, r)}
                  onToggleLocation={(l) => toggle(setSelectedLocations, l)}
                  onToggleSeniority={(s) => toggle(setSelectedSeniority, s)}
                  onApplyProfile={applyToProfile}
                  onApplySearch={useForJobSearch}
                  applying={saving}
                />
              )}
            </div>
          )}

          {!canSuggest && hasCv && !hasCover && (
            <p className="muted" style={{ fontSize: '0.85rem', marginBottom: '1rem' }}>
              Upload your cover letter to unlock <strong>View suggested search criteria</strong>.
            </p>
          )}

          <div className="form-group">
            <label>Summary</label>
            <textarea name="summary" rows={3} value={form.summary} onChange={handleChange} />
          </div>
          <HelpButton
            className="btn-primary"
            onClick={handleSave}
            disabled={saving}
            title="Save Profile"
            help="Saves your profile details. Job search and tailoring use this information to match you with the right roles."
          >
            {saving ? 'Saving...' : 'Save Profile'}
          </HelpButton>
        </div>

        <div>
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ marginBottom: '0.3rem' }}>CV</h3>
            <p className="muted" style={{ marginBottom: '1rem', fontSize: '0.85rem' }}>
              PDF or DOCX. We suggest roles from it.
            </p>
            <label className={`upload-zone${profile?.cv_path ? ' done' : ''}`}>
              <input type="file" accept=".pdf,.docx,.doc,.txt" onChange={(e) => e.target.files[0] && handleFileUpload('cv', e.target.files[0])} />
              {profile?.cv_path ? '✓ CV uploaded — click to replace' : 'Click to upload your CV (PDF or DOCX)'}
            </label>
          </div>
          <div className="card">
            <h3 style={{ marginBottom: '0.3rem' }}>Baseline cover letter</h3>
            <p className="muted" style={{ marginBottom: '1rem', fontSize: '0.85rem' }}>
              Used as a starting point for AI tailoring.
            </p>
            <label className={`upload-zone${profile?.baseline_cover_letter_path ? ' done' : ''}`}>
              <input type="file" accept=".pdf,.docx,.doc,.txt" onChange={(e) => e.target.files[0] && handleFileUpload('cover', e.target.files[0])} />
              {profile?.baseline_cover_letter_path ? '✓ Cover letter uploaded — click to replace' : 'Click to upload a baseline cover letter'}
            </label>
          </div>
        </div>
      </div>
    </div>
  )
}
