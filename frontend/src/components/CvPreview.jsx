const SECTION_TITLES = {
  summary: 'Professional Summary',
  skills: 'Technical Skills',
  soft_skills: 'Soft Skills',
  experience: 'Professional Experience',
  projects: 'Projects',
  certifications: 'Certifications',
  education: 'Education',
}

function experienceLine(item) {
  if (item.role && item.company) return `${item.role} — ${item.company}`
  if (item.heading && item.subheading) return `${item.subheading} — ${item.heading}`
  return item.heading || item.role || item.company || item.subheading || ''
}

function educationLine(item) {
  const degree = item.degree || item.subheading || ''
  const school = item.school || item.heading || ''
  if (degree && school && !school.includes(degree)) return `${degree}, ${school}`
  return school || degree
}

export default function CvPreview({ data }) {
  if (!data) {
    return <p className="muted">CV preview will appear after tailoring.</p>
  }

  const contact = data.contact || {}
  const contactBits = [
    contact.phone,
    contact.email,
    contact.linkedin,
    contact.github,
  ].filter(Boolean)

  return (
    <div className="cv-preview">
      {data.name && <div className="cv-preview__name">{data.name}</div>}
      {data.tagline && <div className="cv-preview__tagline">{data.tagline}</div>}
      {contactBits.length > 0 && (
        <div className="cv-preview__contact">{contactBits.join(' · ')}</div>
      )}
      {(data.sections || []).map((section, idx) => {
        if (!section || typeof section !== 'object') return null
        const type = section.type || ''
        const title = section.title || SECTION_TITLES[type] || type

        return (
          <section key={`${type}-${idx}`} className="cv-preview__section">
            <h5 className="cv-preview__heading">{title}</h5>

            {type === 'summary' && section.text && (
              <p className="cv-preview__text">{section.text}</p>
            )}

            {(type === 'skills' || type === 'soft_skills') && (section.groups || []).map((group, gi) => (
              <p key={gi} className="cv-preview__text">
                {group.label && <strong>{group.label}: </strong>}
                {group.value}
              </p>
            ))}

            {type === 'experience' && (section.items || []).map((item, ii) => (
              <div key={ii} className="cv-preview__item">
                <div className="cv-preview__item-head">
                  <strong>{experienceLine(item)}</strong>
                  {(item.date || item.location) && (
                    <span className="cv-preview__date">
                      {[item.date, item.location].filter(Boolean).join(' | ')}
                    </span>
                  )}
                </div>
                {(item.bullets || []).map((bullet, bi) => (
                  <div key={bi} className="cv-preview__bullet">• {bullet}</div>
                ))}
              </div>
            ))}

            {type === 'projects' && (section.items || []).map((item, ii) => (
              <div key={ii} className="cv-preview__item">
                <strong>{item.heading || item.name}</strong>
                {(item.tech || item.date) && (
                  <div className="cv-preview__sub">
                    {[item.tech, item.date].filter(Boolean).join(' | ')}
                  </div>
                )}
                {(item.bullets || []).map((bullet, bi) => (
                  <div key={bi} className="cv-preview__bullet">• {bullet}</div>
                ))}
              </div>
            ))}

            {type === 'certifications' && (section.items || []).map((item, ii) => (
              <div key={ii} className="cv-preview__bullet">
                • {item.heading}{item.detail ? ` — ${item.detail}` : ''}
              </div>
            ))}

            {type === 'education' && (section.items || []).map((item, ii) => (
              <div key={ii} className="cv-preview__item">
                <div className="cv-preview__item-head">
                  <strong>{educationLine(item)}</strong>
                  {item.date && <span className="cv-preview__date">{item.date}</span>}
                </div>
                {item.location && <div className="cv-preview__sub">{item.location}</div>}
                {item.courses && (
                  <p className="cv-preview__text">
                    {item.courses.toLowerCase().startsWith('relevant')
                      ? item.courses
                      : `Relevant courses: ${item.courses}`}
                  </p>
                )}
              </div>
            ))}
          </section>
        )
      })}
    </div>
  )
}
