import { useEffect, useState } from 'react'
import { api } from '../api'
import CvPreview from './CvPreview'

import ApplyOnSiteButton from './ApplyOnSiteButton'

function sectionOfType(preview, type) {
  return (preview?.sections || []).find((s) => s && s.type === type)
}

function skillChips(preview, cap = 6) {
  const skills = sectionOfType(preview, 'skills')
  const chips = []
  for (const group of skills?.groups || []) {
    for (const part of String(group.value || '').split(',')) {
      const v = part.trim()
      if (v) chips.push(v)
      if (chips.length >= cap) return chips
    }
  }
  return chips
}

export default function TailoredDocuments({
  applicationId, open, onClose, jobUrl, onApply, jobTitle, company,
}) {
  const [meta, setMeta] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [modal, setModal] = useState(null) // 'cv' | 'letter' | null
  const [editing, setEditing] = useState(false)
  const [letterDraft, setLetterDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getTailoredDocuments(applicationId)
      setMeta(data)
      setLetterDraft(data.cover_letter_text || '')
    } catch (err) {
      setError(err.message)
    }
    setLoading(false)
  }

  useEffect(() => {
    if (!open || !applicationId) return undefined
    setModal(null)
    setEditing(false)
    load()
  }, [open, applicationId])

  const handleDownload = async (docType, filename) => {
    try {
      const blob = await api.fetchTailoredDocument(applicationId, docType)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename || 'document.docx'
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message)
    }
  }

  const saveCoverLetter = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.updateCoverLetter(applicationId, letterDraft)
      setMeta((m) => (m ? { ...m, cover_letter_text: letterDraft } : m))
      setEditing(false)
    } catch (err) {
      setError(err.message)
    }
    setSaving(false)
  }

  const closeModal = () => {
    setModal(null)
    setEditing(false)
    setLetterDraft(meta?.cover_letter_text || '')
  }

  if (!open) return null

  const preview = meta?.cv_preview
  const summary = sectionOfType(preview, 'summary')
  const experience = sectionOfType(preview, 'experience')
  const firstJob = (experience?.items || [])[0]
  const chips = skillChips(preview)
  const letterParagraphs = (meta?.cover_letter_text || '')
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean)

  return (
    <div className="tailored-docs-panel">
      <div className="tailored-docs-panel__header">
        <div>
          <h4>Tailored application package</h4>
          <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
            Review your tailored documents, then apply on the job site with the downloads.
          </p>
        </div>
        <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
          Close
        </button>
      </div>

      {loading && <p className="muted">Loading documents…</p>}
      {error && <div className="alert alert-error">{error}</div>}

      {!loading && meta && (
        <>
          <div className="doc-grid">
            {/* CV preview box */}
            <div className="doc-box">
              <div className="doc-box__head">
                <span className="doc-eyebrow">Tailored CV</span>
                {preview && (
                  <button type="button" className="doc-link" onClick={() => setModal('cv')}>
                    View full CV →
                  </button>
                )}
              </div>
              {preview ? (
                <>
                  {preview.name && <div className="doc-box__name">{preview.name}</div>}
                  {preview.tagline && <div className="doc-box__tagline">{preview.tagline}</div>}
                  {summary?.text && <p className="doc-box__text doc-clamp">{summary.text}</p>}
                  {firstJob && (
                    <div>
                      <div className="doc-eyebrow" style={{ marginBottom: '0.35rem' }}>Experience</div>
                      <div className="doc-box__item-title">
                        {[firstJob.role, firstJob.company].filter(Boolean).join(' · ') || firstJob.heading}
                      </div>
                      {firstJob.date && <div className="doc-box__item-date">{firstJob.date}</div>}
                      <ul className="doc-box__bullets">
                        {(firstJob.bullets || []).slice(0, 2).map((b, i) => (
                          <li key={i}>{b}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {chips.length > 0 && (
                    <div className="chip-row">
                      {chips.map((c) => <span key={c} className="chip">{c}</span>)}
                    </div>
                  )}
                </>
              ) : meta.has_cv ? (
                <>
                  <p className="muted" style={{ fontSize: '0.88rem' }}>
                    Preview available for newly tailored applications — download the CV to review.
                  </p>
                  <button
                    type="button"
                    className="doc-link"
                    onClick={() => handleDownload('cv', meta.cv_filename)}
                  >
                    Download CV (.docx) →
                  </button>
                </>
              ) : (
                <p className="muted" style={{ fontSize: '0.88rem' }}>
                  No tailored CV yet. Run "Tailor documents" first.
                </p>
              )}
            </div>

            {/* Cover letter preview box */}
            <div className="doc-box">
              <div className="doc-box__head">
                <span className="doc-eyebrow">Cover letter</span>
                {meta.cover_letter_text && (
                  <button type="button" className="doc-link" onClick={() => setModal('letter')}>
                    View full letter →
                  </button>
                )}
              </div>
              {meta.cover_letter_text ? (
                letterParagraphs.slice(0, 3).map((p, i) => (
                  <p key={i} className="doc-box__text doc-clamp">{p}</p>
                ))
              ) : (
                <p className="muted" style={{ fontSize: '0.88rem' }}>No cover letter text yet.</p>
              )}
            </div>
          </div>

          {jobUrl && onApply && (
            <div className="tailored-docs-panel__apply">
              <p className="muted" style={{ margin: '0.75rem 0 0.5rem', fontSize: '0.85rem' }}>
                Ready to submit? Open the job listing, upload your CV and cover letter, and complete the application.
              </p>
              <ApplyOnSiteButton jobUrl={jobUrl} onApply={onApply} className="btn-primary btn-sm" />
            </div>
          )}

          {/* Document preview modal */}
          {modal && (
            <div className="doc-modal-overlay" onClick={closeModal}>
              <div
                className="doc-modal"
                role="dialog"
                aria-modal="true"
                aria-label={modal === 'cv' ? 'Tailored CV' : 'Tailored cover letter'}
                onClick={(e) => e.stopPropagation()}
              >
                <div className="doc-modal__head">
                  <div>
                    <div className="doc-modal__eyebrow">
                      {modal === 'cv' ? 'Tailored CV' : 'Tailored cover letter'}
                    </div>
                    <h3>{[jobTitle, company].filter(Boolean).join(' — ') || 'Document preview'}</h3>
                  </div>
                  <button type="button" className="doc-modal__close" aria-label="Close" onClick={closeModal}>
                    ×
                  </button>
                </div>

                <div className="doc-modal__body">
                  {modal === 'cv' && <CvPreview data={preview} />}
                  {modal === 'letter' && (
                    editing ? (
                      <>
                        <textarea
                          className="cover-letter-editor"
                          value={letterDraft}
                          onChange={(e) => setLetterDraft(e.target.value)}
                          rows={14}
                        />
                        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                          <button type="button" className="btn-primary btn-sm" disabled={saving} onClick={saveCoverLetter}>
                            {saving ? 'Saving…' : 'Save changes'}
                          </button>
                          <button
                            type="button"
                            className="btn-secondary btn-sm"
                            onClick={() => { setEditing(false); setLetterDraft(meta.cover_letter_text || '') }}
                          >
                            Cancel
                          </button>
                        </div>
                      </>
                    ) : (
                      <div className="doc-modal__letter">
                        {letterParagraphs.map((p, i) => <p key={i}>{p}</p>)}
                      </div>
                    )
                  )}
                </div>

                <div className="doc-modal__footer">
                  {modal === 'letter' && !editing && meta.cover_letter_text && (
                    <button type="button" className="btn-secondary" onClick={() => setEditing(true)}>
                      Edit letter
                    </button>
                  )}
                  <button type="button" className="btn-secondary" onClick={closeModal}>
                    Close
                  </button>
                  {(modal === 'cv' ? meta.has_cv : meta.has_cover_letter) && (
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={() => handleDownload(
                        modal === 'cv' ? 'cv' : 'cover-letter',
                        modal === 'cv' ? meta.cv_filename : meta.cover_letter_filename,
                      )}
                    >
                      Download .docx
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
