/** Prepare scraped job HTML for safe, readable display. */

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function prepareJobDescriptionHtml(raw) {
  if (!raw) return ''
  const trimmed = raw.trim()
  const looksHtml = /<[a-z][\s\S]*>/i.test(trimmed)

  if (!looksHtml) {
    return escapeHtml(trimmed).replace(/\n/g, '<br />')
  }

  const doc = new DOMParser().parseFromString(trimmed, 'text/html')
  doc.querySelectorAll('script, style, img, iframe, noscript, svg').forEach((n) => n.remove())

  // Drop decorative empty spans (common in RSS feeds).
  doc.querySelectorAll('span').forEach((span) => {
    const text = (span.textContent || '').replace(/\u00a0/g, ' ').trim()
    if (!text) span.remove()
  })

  doc.querySelectorAll('*').forEach((el) => {
    ;[...el.attributes].forEach((attr) => {
      if (el.tagName === 'A' && attr.name === 'href') {
        el.setAttribute('target', '_blank')
        el.setAttribute('rel', 'noopener noreferrer')
      } else {
        el.removeAttribute(attr.name)
      }
    })
  })

  return doc.body.innerHTML
}
