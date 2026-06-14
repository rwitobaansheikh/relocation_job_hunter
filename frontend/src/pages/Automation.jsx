import { useEffect, useState } from 'react'
import { api } from '../api'
import HelpButton from '../components/HelpButton'
import OnboardingGuide from '../components/OnboardingGuide'

const AUTOMATION_STEPS = [
  {
    step: 1,
    title: 'Pick one role & location',
    body: 'Each loop targets a single job title and one country or city — e.g. "Machine Learning Engineer" in Netherlands.',
  },
  {
    step: 2,
    title: 'Set your schedule',
    body: 'Choose how often the loop runs and how many applications it sends per day (within your plan limits).',
  },
  {
    step: 3,
    title: 'Enable the loop',
    body: 'Turn it on and the app will search, tailor documents, and send outreach automatically.',
  },
]

const SENIORITY_OPTIONS = [
  { value: 'intern', label: 'Internship' },
  { value: 'entry', label: 'Graduate / Entry' },
  { value: 'mid', label: 'Mid' },
  { value: 'senior', label: 'Senior' },
  { value: 'executive', label: 'Executive' },
]
const POSTED_OPTIONS = [
  { value: 24, label: 'Last 24 hours' },
  { value: 48, label: 'Last 48 hours' },
  { value: 168, label: 'Last week' },
  { value: 336, label: 'Last 2 weeks' },
]

const emptyLoop = () => ({
  name: '',
  role: '',
  locations: '',
  seniority_levels: '',
  posted_within_hours: 48,
  min_salary: '',
  max_salary: '',
  interval_hours: 12,
  daily_send_cap: 5,
  per_domain_cap: 2,
  max_tailor_per_run: 5,
  enabled: true,
})

function LoopForm({ initial, onCancel, onSave, saving, autoCap }) {
  const [form, setForm] = useState(initial)
  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }))
  const levels = (form.seniority_levels || '').split(',').map((s) => s.trim()).filter(Boolean)
  const toggleLevel = (val) => {
    const next = levels.includes(val) ? levels.filter((l) => l !== val) : [...levels, val]
    set('seniority_levels', next.join(','))
  }

  return (
    <div className="card" style={{ marginBottom: '1rem', borderColor: 'var(--accent)' }}>
      <div className="filter-grid">
        <div className="form-group">
          <label>Loop name</label>
          <input value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="e.g. Frontend roles in Germany" />
        </div>
        <div className="form-group">
          <label>Target role *</label>
          <input value={form.role} onChange={(e) => set('role', e.target.value)} placeholder="e.g. Frontend Engineer" />
        </div>
        <div className="form-group">
          <label>Location (single country/city)</label>
          <input 
            value={form.locations} 
            onChange={(e) => set('locations', e.target.value.replace(/,/g, ''))} 
            placeholder="e.g. Netherlands — blank uses your profile countries" 
          />
        </div>
        <div className="form-group">
          <label>Posted within</label>
          <select value={form.posted_within_hours} onChange={(e) => set('posted_within_hours', Number(e.target.value))}>
            {POSTED_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <div className="form-group">
          <label>Min salary</label>
          <input type="number" min="0" step="1000" value={form.min_salary} onChange={(e) => set('min_salary', e.target.value)} />
        </div>
        <div className="form-group">
          <label>Max salary</label>
          <input type="number" min="0" step="1000" value={form.max_salary} onChange={(e) => set('max_salary', e.target.value)} />
        </div>
        <div className="form-group">
          <label>Run every (hours)</label>
          <input type="number" min="1" max="168" value={form.interval_hours} onChange={(e) => set('interval_hours', Number(e.target.value))} />
        </div>
        <div className="form-group">
          <label>Auto applies / day {autoCap ? `(max ${autoCap})` : ''}</label>
          <input type="number" min="0" max={autoCap || 500} value={form.daily_send_cap} onChange={(e) => set('daily_send_cap', Number(e.target.value))} />
        </div>
        <div className="form-group">
          <label>Emails per company</label>
          <input type="number" min="1" max="50" value={form.per_domain_cap} onChange={(e) => set('per_domain_cap', Number(e.target.value))} />
        </div>
        <div className="form-group">
          <label>Tailor per run</label>
          <input type="number" min="1" max="50" value={form.max_tailor_per_run} onChange={(e) => set('max_tailor_per_run', Number(e.target.value))} />
        </div>
      </div>

      <div className="form-group">
        <label>Seniority levels</label>
        <div className="checkbox-row">
          {SENIORITY_OPTIONS.map((o) => (
            <label key={o.value} className="checkbox-pill">
              <input type="checkbox" checked={levels.includes(o.value)} onChange={() => toggleLevel(o.value)} />
              {o.label}
            </label>
          ))}
        </div>
      </div>

      <label className="switch-row">
        <input type="checkbox" checked={form.enabled} onChange={(e) => set('enabled', e.target.checked)} />
        Enabled
      </label>

      <div style={{ display: 'flex', gap: '0.6rem', marginTop: '0.8rem' }}>
        <HelpButton
          className="btn-primary"
          disabled={saving || !form.role.trim()}
          onClick={() => onSave(form)}
          title="Save loop"
          help="Saves this automation loop. It will search, tailor, and send applications on the schedule you set."
        >
          {saving ? 'Saving…' : 'Save loop'}
        </HelpButton>
        <HelpButton
          className="btn-secondary"
          onClick={onCancel}
          disabled={saving}
          title="Cancel"
          help="Close the form without saving changes to this loop."
        >
          Cancel
        </HelpButton>
      </div>
    </div>
  )
}

export default function Automation() {
  const [loops, setLoops] = useState([])
  const [billing, setBilling] = useState(null)
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState(null)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(null) // 'new' | loop id

  const load = async () => {
    setLoading(true)
    try {
      const [l, b, r] = await Promise.all([api.getLoops(), api.getBilling(), api.getAutomationRuns()])
      setLoops(l)
      setBilling(b)
      setRuns(r)
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const normalize = (form) => {
    const payload = { ...form }
    payload.min_salary = form.min_salary === '' ? null : Number(form.min_salary)
    payload.max_salary = form.max_salary === '' ? null : Number(form.max_salary)
    return payload
  }

  const saveNew = async (form) => {
    setSaving(true)
    setMessage(null)
    try {
      await api.createLoop(normalize(form))
      setEditing(null)
      await load()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
    setSaving(false)
  }

  const saveEdit = async (id, form) => {
    setSaving(true)
    setMessage(null)
    try {
      await api.updateLoop(id, normalize(form))
      setEditing(null)
      await load()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
    setSaving(false)
  }

  const toggle = async (loop) => {
    setMessage(null)
    try {
      await api.updateLoop(loop.id, { enabled: !loop.enabled })
      await load()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
  }

  const remove = async (loop) => {
    if (!window.confirm(`Delete loop "${loop.name || loop.role}"?`)) return
    try {
      await api.deleteLoop(loop.id)
      await load()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
  }

  if (loading) return <p>Loading...</p>

  const maxLoops = billing?.limits?.max_loops ?? 0
  const activeCount = loops.filter((l) => l.enabled).length
  const canAutomate = maxLoops > 0
  const atCap = activeCount >= maxLoops
  const autoCap = billing?.limits?.auto_per_loop_per_day

  return (
    <div>
      <h2 className="page-title">Automation</h2>
      <p className="page-subtitle">
        Each loop searches one role in one location, tailors documents, and sends applications on a schedule.
      </p>

      {loops.length === 0 && editing !== 'new' && (
        <OnboardingGuide
          storageKey="jh_onboarding_automation"
          title="Setting up your first automation loop"
          steps={AUTOMATION_STEPS}
        />
      )}

      {message && <div className={`alert alert-${message.type}`}>{message.text}</div>}

      <div className="card" style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.6rem' }}>
        <div>
          <strong>{activeCount} / {maxLoops}</strong> active loops on the{' '}
          <span style={{ textTransform: 'capitalize' }}>{billing?.plan}</span> plan
          {autoCap ? ` · up to ${autoCap} auto applies/loop/day` : ''}
        </div>
        {!canAutomate ? (
          <a className="btn-primary" href="/app/billing">Upgrade to enable automation</a>
        ) : (
          <HelpButton
            className="btn-primary"
            disabled={editing === 'new' || atCap}
            onClick={() => setEditing('new')}
            title="Add loop"
            help="Create a new automation loop that searches one role on a timer, tailors documents, and sends applications for you."
          >
            + Add loop
          </HelpButton>
        )}
      </div>

      {atCap && canAutomate && (
        <div className="alert alert-info">
          You've reached your plan's loop limit. <a href="/app/billing">Upgrade</a> for more, or disable a loop.
        </div>
      )}

      {editing === 'new' && (
        <LoopForm initial={emptyLoop()} autoCap={autoCap} saving={saving} onCancel={() => setEditing(null)} onSave={saveNew} />
      )}

      {loops.length === 0 && editing !== 'new' ? (
        <div className="empty-state"><p>No automation loops yet.</p></div>
      ) : (
        <div className="application-list">
          {loops.map((loop) => (
            editing === loop.id ? (
              <LoopForm
                key={loop.id}
                initial={{
                  ...loop,
                  min_salary: loop.min_salary ?? '',
                  max_salary: loop.max_salary ?? '',
                }}
                autoCap={autoCap}
                saving={saving}
                onCancel={() => setEditing(null)}
                onSave={(form) => saveEdit(loop.id, form)}
              />
            ) : (
              <article key={loop.id} className="application-card">
                <header className="application-card__header">
                  <div className="application-card__info">
                    <h3>{loop.name || loop.role || 'Untitled loop'}</h3>
                    <p className="application-card__meta">
                      {loop.role || 'Any role'} · {loop.locations || 'profile countries'} · every {loop.interval_hours}h
                    </p>
                    <div className="application-card__tags">
                      <span className={`badge badge-${loop.enabled ? 'applied' : 'rejected'}`}>
                        {loop.enabled ? 'enabled' : 'disabled'}
                      </span>
                      <span className="muted" style={{ fontSize: '0.85rem' }}>
                        up to {loop.daily_send_cap}/day
                        {loop.last_run_at && ` · last run ${new Date(loop.last_run_at).toLocaleString()}`}
                      </span>
                    </div>
                  </div>
                </header>
                <div className="application-card__primary">
                  <HelpButton
                    className="btn-secondary"
                    onClick={() => toggle(loop)}
                    title={loop.enabled ? 'Disable' : 'Enable'}
                    help={loop.enabled ? 'Pause this loop.' : 'Resume this loop.'}
                  >
                    {loop.enabled ? 'Disable' : 'Enable'}
                  </HelpButton>
                  <HelpButton
                    className="btn-secondary"
                    onClick={() => setEditing(loop.id)}
                    title="Edit"
                    help="Change role, location, schedule, or daily limits."
                  >
                    Edit
                  </HelpButton>
                  <HelpButton
                    className="btn-danger"
                    onClick={() => remove(loop)}
                    title="Delete"
                    help="Remove this loop permanently."
                  >
                    Delete
                  </HelpButton>
                </div>
              </article>
            )
          ))}
        </div>
      )}

      <div className="card" style={{ marginTop: '1.5rem' }}>
        <h3 style={{ marginBottom: '1rem' }}>Recent automation activity</h3>
        {runs.length === 0 ? (
          <p className="muted">No automation runs yet.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Started</th>
                  <th>Status</th>
                  <th>New jobs</th>
                  <th>Tailored</th>
                  <th>Sent</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>{new Date(r.started_at).toLocaleString()}</td>
                    <td>
                      <span className={`badge badge-${r.status === 'success' ? 'applied' : r.status === 'error' ? 'rejected' : 'pending'}`}>
                        {r.status}
                      </span>
                    </td>
                    <td>{r.jobs_found}</td>
                    <td>{r.jobs_tailored}</td>
                    <td>{r.emails_sent}</td>
                    <td className="muted" style={{ maxWidth: 280, whiteSpace: 'normal' }}>{r.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
