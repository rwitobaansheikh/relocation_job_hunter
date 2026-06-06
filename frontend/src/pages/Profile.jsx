import { useState } from 'react'
import { api } from '../api'
import { useProfile } from '../ProfileContext'

export default function Profile() {
  const { profile, setProfile, refreshProfile } = useProfile()
  const [form, setForm] = useState({
    full_name: profile?.full_name || '',
    email: profile?.email || '',
    phone: profile?.phone || '',
    location: profile?.location || '',
    linkedin_url: profile?.linkedin_url || '',
    skills: profile?.skills || '',
    summary: profile?.summary || '',
    target_roles: profile?.target_roles || '',
    target_countries: profile?.target_countries || '',
  })
  const [message, setMessage] = useState(null)
  const [saving, setSaving] = useState(false)

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value })

  const handleSave = async () => {
    setSaving(true)
    setMessage(null)
    try {
      if (profile?.id) {
        const updated = await api.updateProfile(profile.id, form)
        setProfile(updated)
      } else {
        const created = await api.createProfile(form)
        setProfile(created)
      }
      setMessage({ type: 'success', text: 'Profile saved successfully' })
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
    setSaving(false)
  }

  const handleFileUpload = async (type, file) => {
    if (!profile?.id) {
      setMessage({ type: 'error', text: 'Save your profile first before uploading files' })
      return
    }
    setMessage(null)
    try {
      if (type === 'cv') await api.uploadCV(profile.id, file)
      else await api.uploadCoverLetter(profile.id, file)
      await refreshProfile()
      setMessage({ type: 'success', text: `${type === 'cv' ? 'CV' : 'Cover letter'} uploaded successfully` })
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
  }

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
            <input name="location" value={form.location} onChange={handleChange} placeholder="e.g. India" />
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
            <input name="target_roles" value={form.target_roles} onChange={handleChange} placeholder="Software Engineer, Backend Developer" />
          </div>
          <div className="form-group">
            <label>Target Countries (comma-separated)</label>
            <input name="target_countries" value={form.target_countries} onChange={handleChange} placeholder="Germany, Netherlands, UK" />
          </div>
          <div className="form-group">
            <label>Summary</label>
            <textarea name="summary" rows={3} value={form.summary} onChange={handleChange} />
          </div>
          <button className="btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Save Profile'}
          </button>
        </div>

        <div>
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ marginBottom: '1rem' }}>Upload CV</h3>
            <label className="file-upload">
              <input type="file" accept=".pdf,.docx,.doc,.txt" onChange={(e) => e.target.files[0] && handleFileUpload('cv', e.target.files[0])} />
              <p>{profile?.cv_path ? '✓ CV uploaded — click to replace' : 'Drop or click to upload CV (PDF, DOCX, TXT)'}</p>
            </label>
          </div>
          <div className="card">
            <h3 style={{ marginBottom: '1rem' }}>Upload Baseline Cover Letter</h3>
            <label className="file-upload">
              <input type="file" accept=".pdf,.docx,.doc,.txt" onChange={(e) => e.target.files[0] && handleFileUpload('cover', e.target.files[0])} />
              <p>{profile?.baseline_cover_letter_path ? '✓ Cover letter uploaded — click to replace' : 'Drop or click to upload cover letter'}</p>
            </label>
          </div>
        </div>
      </div>
    </div>
  )
}
