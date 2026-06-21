const SECTION_TITLES = {
  summary: 'Summary',
  education: 'Education',
  experience: 'Experience',
  projects: 'Projects',
  skills: 'Skills',
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

            {type === 'skills' && (section.groups || []).map((group, gi) => (
              <p key={gi} className="cv-preview__text">
                {group.label && <strong>{group.label}: </strong>}
                {group.value}
              </p>
            ))}

            {(type === 'experience' || type === 'education') && (section.items || []).map((item, ii) => (
              <div key={ii} className="cv-preview__item">
                <div className="cv-preview__item-head">
                  <strong>{item.heading}</strong>
                  {item.date && <span className="cv-preview__date">{item.date}</span>}
                </div>
                {(item.subheading || item.location) && (
                  <div className="cv-preview__sub">
                    {item.subheading}
                    {item.subheading && item.location ? ' · ' : ''}
                    {item.location}
                  </div>
                )}
                {(item.bullets || []).map((bullet, bi) => (
                  <div key={bi} className="cv-preview__bullet">• {bullet}</div>
                ))}
              </div>
            ))}

            {type === 'projects' && (section.items || []).map((item, ii) => (
              <div key={ii} className="cv-preview__item">
                <strong>{item.heading || item.name}</strong>
                {item.text && <p className="cv-preview__text">{item.text}</p>}
                {(item.bullets || []).map((bullet, bi) => (
                  <div key={bi} className="cv-preview__bullet">• {bullet}</div>
                ))}
              </div>
            ))}
          </section>
        )
      })}
    </div>
  )
}
