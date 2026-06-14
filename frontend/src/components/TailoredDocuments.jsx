import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

export default function TailoredDocuments({ applicationId, open, onClose }) {
  const [meta, setMeta] = useState(null)
  const [cvUrl, setCvUrl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const cvUrlRef = useRef(null)

  useEffect(() => {
    if (!open || !applicationId) return undefined

    const load = async () => {
      setLoading(true)
      setError(null)
      setMeta(null)
      if (cvUrlRef.current) {
        URL.revokeObjectURL(cvUrlRef.current)
        cvUrlRef.current = null
        setCvUrl(null)
      }
      try {
        const data = await api.getTailoredDocuments(applicationId)
        setMeta(data)
        if (data.has_cv) {
          const blob = await api.fetchTailoredDocument(applicationId, 'cv')
          const url = URL.createObjectURL(blob)
          cvUrlRef.current = url
          setCvUrl(url)
        }
      } catch (err) {
        setError(err.message)
      }
      setLoading(false)
    }
    load()

    return () => {
      if (cvUrlRef.current) {
        URL.revokeObjectURL(cvUrlRef.current)
        cvUrlRef.current = null
      }
    }
  }, [open, applicationId])

  const handleDownload = async (docType, filename) => {
    try {
      const blob = await api.fetchTailoredDocument(applicationId, docType)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename || 'document.pdf'
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
          <div className="tailored-docs-panel__actions">
            {meta.has_cv && (
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => handleDownload('cv', meta.cv_filename)}
              >
                Download CV
              </button>
            )}
            {meta.has_cover_letter && (
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => handleDownload('cover-letter', meta.cover_letter_filename)}
              >
                Download Cover Letter
              </button>
            )}
          </div>

          {cvUrl && (
            <div className="tailored-docs-panel__preview">
              <div className="tailored-docs-panel__label">CV preview</div>
              <iframe title="Tailored CV" src={cvUrl} />
            </div>
          )}

          {meta.cover_letter_text && (
            <div className="tailored-docs-panel__letter">
              <div className="tailored-docs-panel__label">Cover letter</div>
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
