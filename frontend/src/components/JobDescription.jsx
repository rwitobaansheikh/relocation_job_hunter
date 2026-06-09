import { useMemo } from 'react'
import { prepareJobDescriptionHtml } from '../utils/html'

export default function JobDescription({ html }) {
  const safeHtml = useMemo(() => prepareJobDescriptionHtml(html), [html])
  if (!safeHtml) return <p className="muted">No description available.</p>
  return (
    <div
      className="job-description job-description-html"
      dangerouslySetInnerHTML={{ __html: safeHtml }}
    />
  )
}
