import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../AuthContext'

function PasswordSection() {
  const { user } = useAuth()
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [message, setMessage] = useState(null)
  const [saving, setSaving] = useState(false)
  const oauthAccount = Boolean(user?.oauth_provider)

  const submit = async (e) => {
    e.preventDefault()
    if (form.next.length < 8) {
      setMessage({ type: 'error', text: 'New password must be at least 8 characters' })
      return
    }
    if (form.next !== form.confirm) {
      setMessage({ type: 'error', text: 'Passwords do not match' })
      return
    }
    setSaving(true)
    setMessage(null)
    try {
      await api.changePassword({
        current_password: form.current,
        new_password: form.next,
      })
      setForm({ current: '', next: '', confirm: '' })
      setMessage({ type: 'success', text: 'Password updated successfully' })
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
    setSaving(false)
  }

  return (
    <form onSubmit={submit}>
      {message && <div className={`alert alert-${message.type}`}>{message.text}</div>}
      {oauthAccount && (
        <p className="muted" style={{ marginBottom: '1rem' }}>
          You signed in with {user.oauth_provider}. Set a password here to also log in with email and password.
        </p>
      )}
      {!oauthAccount && (
        <div className="form-group">
          <label>Current password</label>
          <input
            type="password"
            value={form.current}
            onChange={(e) => setForm((f) => ({ ...f, current: e.target.value }))}
            required
          />
        </div>
      )}
      <div className="form-group">
        <label>New password</label>
        <input
          type="password"
          value={form.next}
          onChange={(e) => setForm((f) => ({ ...f, next: e.target.value }))}
          required
          minLength={8}
        />
      </div>
      <div className="form-group">
        <label>Confirm new password</label>
        <input
          type="password"
          value={form.confirm}
          onChange={(e) => setForm((f) => ({ ...f, confirm: e.target.value }))}
          required
          minLength={8}
        />
      </div>
      <button type="submit" className="btn-primary" disabled={saving}>
        {saving ? 'Updating…' : oauthAccount ? 'Set password' : 'Change password'}
      </button>
    </form>
  )
}

export default function Settings() {
  const { user, logout } = useAuth()
  const [settings, setSettings] = useState(null)
  const [form, setForm] = useState({})
  const [message, setMessage] = useState(null)
  const [saving, setSaving] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [showDelete, setShowDelete] = useState(false)
  const [deletePassword, setDeletePassword] = useState('')
  const [deleteConfirm, setDeleteConfirm] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState(null)

  useEffect(() => {
    api
      .getSettings()
      .then((s) => {
        setSettings(s)
        setForm({
          smtp_host: s.smtp_host || '',
          smtp_port: s.smtp_port || 587,
          smtp_password: '',
          gemini_api_key: '',
          rocketreach_api_key: '',
        })
      })
      .catch((err) => setMessage({ type: 'error', text: err.message }))
  }, [])

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }))

  const save = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const payload = { ...form }
      if (!payload.smtp_password) delete payload.smtp_password
      if (!payload.gemini_api_key) delete payload.gemini_api_key
      if (!payload.rocketreach_api_key) delete payload.rocketreach_api_key
      const updated = await api.updateSettings(payload)
      setSettings(updated)
      setForm((f) => ({ ...f, smtp_password: '', gemini_api_key: '', rocketreach_api_key: '' }))
      setMessage({ type: 'success', text: 'Settings saved' })
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
    setSaving(false)
  }

  const deleteAccount = async () => {
    setDeleting(true)
    setDeleteError(null)
    try {
      await api.deleteAccount(deletePassword)
      // Account and all data are gone — drop the session and return to landing.
      logout()
      window.location.href = '/'
    } catch (err) {
      setDeleteError(err.message)
      setDeleting(false)
    }
  }

  if (!settings) return <p>Loading...</p>

  return (
    <div>
      <h2 className="page-title">Settings</h2>
      <p className="page-subtitle">Your sending identity and API keys.</p>

      {message && <div className={`alert alert-${message.type}`}>{message.text}</div>}

      <div className="card">
        <h3 style={{ marginBottom: '1rem' }}>Outreach mailbox (your login email)</h3>
        <p className="muted" style={{ marginBottom: '1rem' }}>
          Emails to recruiters are sent from <strong>{user?.email || 'your login email'}</strong>.
          Add your mailbox app password below (Gmail users: create an App Password).
        </p>
        <p className="muted" style={{ marginBottom: '1rem', fontSize: '0.85rem' }}>
          Trial reminders, test previews, and billing notices come from{' '}
          <strong>email@jobapplicationflow.com</strong> — not from this mailbox.
        </p>
        <div className="form-group">
          <label>Send outreach as</label>
          <input value={user?.email || ''} readOnly disabled />
        </div>
        <div className="form-group">
          <label>SMTP Host</label>
          <input value={form.smtp_host} onChange={(e) => set('smtp_host', e.target.value)} placeholder="smtp.gmail.com" />
        </div>
        <div className="form-group">
          <label>SMTP Port</label>
          <input type="number" value={form.smtp_port} onChange={(e) => set('smtp_port', Number(e.target.value))} />
        </div>
        <div className="form-group">
          <label>SMTP Password {settings.smtp_password_set && <span className="muted">(set - leave blank to keep)</span>}</label>
          <input
            type="password"
            value={form.smtp_password}
            onChange={(e) => set('smtp_password', e.target.value)}
            placeholder={settings.smtp_password_set ? '••••••••' : 'app password'}
          />
        </div>
      </div>

      <div className="card" style={{ marginTop: '1.5rem' }}>
        <button className="btn-secondary" onClick={() => setShowAdvanced((v) => !v)}>
          {showAdvanced ? 'Hide' : 'Show'} advanced: API key overrides
        </button>
        {showAdvanced && (
          <div style={{ marginTop: '1rem' }}>
            <p className="muted" style={{ marginBottom: '1rem' }}>
              Optional. The app uses a local Ollama LLM by default. These overrides only apply if the server is set to cloud mode (<code>LLM_PROVIDER=gemini</code>) or for RocketReach contact lookup.
            </p>
            <div className="form-group">
              <label>Gemini API key (cloud mode only) {settings.gemini_override_set && <span className="muted">(set)</span>}</label>
              <input type="password" value={form.gemini_api_key} onChange={(e) => set('gemini_api_key', e.target.value)} placeholder="leave blank to keep / use shared" />
            </div>
            <div className="form-group">
              <label>RocketReach API key {settings.rocketreach_override_set && <span className="muted">(set)</span>}</label>
              <input type="password" value={form.rocketreach_api_key} onChange={(e) => set('rocketreach_api_key', e.target.value)} placeholder="leave blank to keep / use shared" />
            </div>
          </div>
        )}
      </div>

      <div style={{ marginTop: '1.5rem' }}>
        <button className="btn-primary" onClick={save} disabled={saving}>
          {saving ? 'Saving...' : 'Save settings'}
        </button>
      </div>

      <div className="card" style={{ marginTop: '1.5rem' }}>
        <h3 style={{ marginBottom: '1rem' }}>Account password</h3>
        <PasswordSection />
      </div>

      <div className="card danger-zone" style={{ marginTop: '2rem' }}>
        <h3 style={{ marginBottom: '0.4rem' }}>Delete account</h3>
        <p className="muted" style={{ marginBottom: '1rem' }}>
          Permanently delete your account, cancel any active subscription, and erase all of your
          data — profile, uploaded and generated documents, applications, outreach emails,
          automation loops, usage history and any reviews/messages you submitted. This action is
          irreversible and cannot be undone.
        </p>
        {!showDelete ? (
          <button className="btn-danger" onClick={() => setShowDelete(true)}>
            Delete my account & data
          </button>
        ) : (
          <div>
            {deleteError && <div className="alert alert-error">{deleteError}</div>}
            <div className="form-group">
              <label>Confirm your password</label>
              <input
                type="password"
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                placeholder="your password"
              />
            </div>
            <div className="form-group">
              <label>Type DELETE to confirm</label>
              <input
                value={deleteConfirm}
                onChange={(e) => setDeleteConfirm(e.target.value)}
                placeholder="DELETE"
              />
            </div>
            <div style={{ display: 'flex', gap: '0.6rem' }}>
              <button
                className="btn-danger"
                disabled={deleting || deleteConfirm !== 'DELETE' || !deletePassword}
                onClick={deleteAccount}
              >
                {deleting ? 'Deleting…' : 'Permanently delete'}
              </button>
              <button
                className="btn-secondary"
                disabled={deleting}
                onClick={() => { setShowDelete(false); setDeletePassword(''); setDeleteConfirm(''); setDeleteError(null) }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
