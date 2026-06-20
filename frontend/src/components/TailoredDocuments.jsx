import { useEffect, useState } from 'react'
import { api } from '../api'

export default function TailoredDocuments({ applicationId, open, onClose }) {
  const [meta, setMeta] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!open || !applicationId) return undefined

    const load = async () => {
      setLoading(true)
      setError(null)
      setMeta(null)
      try {
        const data = await api.getTailoredDocuments(applicationId)
        setMeta(data)
      } catch (err) {
        setError(err.message)
      }
      setLoading(false)
    }
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

  if (!open) return null

  return (
    <div className="tailored-docs-panel">
      <div className="tailored-docs-panel__header">
        <h4>Tailored CV & Cover Letter</h4>
        <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
          Close
        </button>
      </div>

      {loading && <p className="muted">Loading documents…</p>}
      {error && <div className="alert alert-error">{error}</div>}

      {!loading && meta && (
        <>
          <p className="muted" style={{ marginBottom: '0.75rem' }}>
            Documents are generated as Word (.docx) files for ATS compatibility. Download to open in Microsoft Word.
          </p>
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

          {meta.cover_letter_text && (
            <div className="tailored-docs-panel__letter">
              <div className="tailored-docs-panel__label">Cover letter preview</div>
              <div className="tailored-docs-panel__letter-body">{meta.cover_letter_text}</div>
            </div>
          )}

          {!meta.has_cv && !meta.has_cover_letter && (
            <p className="muted">No tailored documents found. Run &quot;Tailor Docs&quot; first.</p>
          )}
        </>
      )}
    </div>
  )
}
