import { useEffect, useState } from 'react'
import { api } from '../api'
import CvPreview from './CvPreview'

import ApplyOnSiteButton from './ApplyOnSiteButton'

export default function TailoredDocuments({ applicationId, open, onClose, jobUrl, onApply }) {
  const [meta, setMeta] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('cv')
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
    setTab('cv')
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

  if (!open) return null

  return (
    <div className="tailored-docs-panel">
      <div className="tailored-docs-panel__header">
        <div>
          <h4>Tailored application package</h4>
          <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
            Download your tailored documents, then apply on the job site with them.
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
          <div className="doc-tabs">
            <button
              type="button"
              className={`doc-tab${tab === 'cv' ? ' doc-tab--active' : ''}`}
              onClick={() => setTab('cv')}
            >
              CV preview
            </button>
            <button
              type="button"
              className={`doc-tab${tab === 'letter' ? ' doc-tab--active' : ''}`}
              onClick={() => setTab('letter')}
            >
              Cover letter
            </button>
          </div>

          <div className="tailored-docs-panel__actions">
            {meta.has_cv && (
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => handleDownload('cv', meta.cv_filename)}
              >
                Download CV (.docx)
              </button>
            )}
            {meta.has_cover_letter && (
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => handleDownload('cover-letter', meta.cover_letter_filename)}
              >
                Download Cover Letter (.docx)
              </button>
            )}
          </div>

          {tab === 'cv' && (
            <div className="tailored-docs-panel__preview">
              {meta.cv_preview ? (
                <CvPreview data={meta.cv_preview} />
              ) : meta.has_cv ? (
                <p className="muted">Download the CV to review — preview available for newly tailored applications.</p>
              ) : (
                <p className="muted">No tailored CV yet. Run &quot;Tailor documents&quot; first.</p>
              )}
            </div>
          )}

          {tab === 'letter' && (
            <div className="tailored-docs-panel__letter">
              <div className="tailored-docs-panel__label-row">
                <div className="tailored-docs-panel__label">Cover letter preview</div>
                {!editing && meta.cover_letter_text && (
                  <button type="button" className="btn-secondary btn-sm" onClick={() => setEditing(true)}>
                    Edit
                  </button>
                )}
              </div>
              {editing ? (
                <>
                  <textarea
                    className="cover-letter-editor"
                    value={letterDraft}
                    onChange={(e) => setLetterDraft(e.target.value)}
                    rows={12}
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
                <div className="tailored-docs-panel__letter-body">
                  {meta.cover_letter_text || 'No cover letter text yet.'}
                </div>
              )}
            </div>
          )}

          {jobUrl && onApply && (
            <div className="tailored-docs-panel__apply">
              <p className="muted" style={{ margin: '0.75rem 0 0.5rem', fontSize: '0.85rem' }}>
                Ready to submit? Open the job listing, upload your CV and cover letter, and complete the application.
              </p>
              <ApplyOnSiteButton jobUrl={jobUrl} onApply={onApply} className="btn-primary btn-sm" />
            </div>
          )}
        </>
      )}
    </div>
  )
}
