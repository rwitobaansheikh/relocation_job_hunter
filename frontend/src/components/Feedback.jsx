import { useEffect, useState } from 'react'
import { api, CONTACT_EMAIL } from '../api'

function Stars({ value, onChange }) {
  const [hover, setHover] = useState(0)
  return (
    <div className="stars" role="radiogroup" aria-label="Rating">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          className={`star ${(hover || value) >= n ? 'on' : ''}`}
          onMouseEnter={() => onChange && setHover(n)}
          onMouseLeave={() => onChange && setHover(0)}
          onClick={() => onChange && onChange(n)}
          aria-checked={value === n}
          role="radio"
          disabled={!onChange}
        >
          ★
        </button>
      ))}
    </div>
  )
}

export function ReviewsSection() {
  const [reviews, setReviews] = useState([])
  const [form, setForm] = useState({ name: '', email: '', rating: 5, message: '' })
  const [status, setStatus] = useState(null)
  const [saving, setSaving] = useState(false)

  const load = () => api.getReviews().then(setReviews).catch(() => {})
  useEffect(() => { load() }, [])

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setStatus(null)
    try {
      const payload = { name: form.name.trim(), rating: form.rating, message: form.message.trim() }
      if (form.email.trim()) payload.email = form.email.trim()
      await api.submitReview(payload)
      setForm({ name: '', email: '', rating: 5, message: '' })
      setStatus({ type: 'success', text: 'Thanks for your review!' })
      load()
    } catch (err) {
      setStatus({ type: 'error', text: err.message })
    }
    setSaving(false)
  }

  return (
    <section id="reviews" className="fb-section">
      <h2 className="section-heading">What users say</h2>
      <p className="section-sub">Real feedback from people running their job search with us.</p>

      {reviews.length > 0 && (
        <div className="review-grid">
          {reviews.map((r) => (
            <div key={r.id} className="card review-card">
              <Stars value={r.rating || 0} />
              <p className="review-msg">“{r.message}”</p>
              <div className="review-author">— {r.name}</div>
            </div>
          ))}
        </div>
      )}

      <div className="card fb-form-card">
        <h3 style={{ marginBottom: '0.8rem' }}>Leave a review</h3>
        {status && <div className={`alert alert-${status.type}`}>{status.text}</div>}
        <form onSubmit={submit}>
          <div className="form-group">
            <label>Your rating</label>
            <Stars value={form.rating} onChange={(n) => set('rating', n)} />
          </div>
          <div className="form-group">
            <label>Name</label>
            <input value={form.name} onChange={(e) => set('name', e.target.value)} required maxLength={120} />
          </div>
          <div className="form-group">
            <label>Email (optional)</label>
            <input type="email" value={form.email} onChange={(e) => set('email', e.target.value)} />
          </div>
          <div className="form-group">
            <label>Your review</label>
            <textarea rows={3} value={form.message} onChange={(e) => set('message', e.target.value)} required maxLength={2000} />
          </div>
          <button className="btn-primary" disabled={saving || !form.name.trim() || !form.message.trim()}>
            {saving ? 'Submitting…' : 'Submit review'}
          </button>
        </form>
      </div>
    </section>
  )
}

export function ContactSection() {
  const [form, setForm] = useState({ name: '', email: '', subject: '', message: '' })
  const [status, setStatus] = useState(null)
  const [saving, setSaving] = useState(false)

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setStatus(null)
    try {
      await api.submitContact({
        name: form.name.trim(),
        email: form.email.trim(),
        subject: form.subject.trim(),
        message: form.message.trim(),
      })
      setForm({ name: '', email: '', subject: '', message: '' })
      setStatus({ type: 'success', text: 'Message sent — we’ll get back to you soon.' })
    } catch (err) {
      setStatus({ type: 'error', text: err.message })
    }
    setSaving(false)
  }

  return (
    <section id="contact" className="fb-section">
      <h2 className="section-heading">Contact us</h2>
      <p className="section-sub">
        Questions, feedback or partnership ideas? Email{' '}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> or use the form below.
      </p>

      <div className="card fb-form-card">
        {status && <div className={`alert alert-${status.type}`}>{status.text}</div>}
        <form onSubmit={submit}>
          <div className="form-group">
            <label>Name</label>
            <input value={form.name} onChange={(e) => set('name', e.target.value)} required maxLength={120} />
          </div>
          <div className="form-group">
            <label>Email</label>
            <input type="email" value={form.email} onChange={(e) => set('email', e.target.value)} required />
          </div>
          <div className="form-group">
            <label>Subject (optional)</label>
            <input value={form.subject} onChange={(e) => set('subject', e.target.value)} maxLength={200} />
          </div>
          <div className="form-group">
            <label>Message</label>
            <textarea rows={4} value={form.message} onChange={(e) => set('message', e.target.value)} required maxLength={4000} />
          </div>
          <button className="btn-primary" disabled={saving || !form.name.trim() || !form.email.trim() || !form.message.trim()}>
            {saving ? 'Sending…' : 'Send message'}
          </button>
        </form>
      </div>
    </section>
  )
}
