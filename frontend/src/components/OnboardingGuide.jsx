import { useState } from 'react'
import { Link } from 'react-router-dom'

/**
 * Dismissible step-by-step guide stored in localStorage.
 * @param {string} storageKey - localStorage key, e.g. 'jh_onboarding_app'
 * @param {string} title
 * @param {Array<{step: number, title: string, body: string, to?: string, linkLabel?: string}>} steps
 */
export default function OnboardingGuide({ storageKey, title, steps }) {
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(storageKey) === '1'
    } catch {
      return false
    }
  })

  if (dismissed) return null

  const dismiss = () => {
    try {
      localStorage.setItem(storageKey, '1')
    } catch {
      /* ignore */
    }
    setDismissed(true)
  }

  return (
    <div className="onboarding-guide">
      <div className="onboarding-guide__header">
        <div>
          <div className="onboarding-guide__eyebrow">Getting started</div>
          <h3 className="onboarding-guide__title">{title}</h3>
        </div>
        <button type="button" className="onboarding-guide__dismiss" onClick={dismiss} aria-label="Dismiss guide">
          ×
        </button>
      </div>
      <ol className="onboarding-guide__steps">
        {steps.map((s) => (
          <li key={s.step} className="onboarding-guide__step">
            <span className="onboarding-guide__step-num">{s.step}</span>
            <div>
              <strong>{s.title}</strong>
              <p>{s.body}</p>
              {s.to && (
                <Link to={s.to} className="onboarding-guide__link">
                  {s.linkLabel || 'Go →'}
                </Link>
              )}
            </div>
          </li>
        ))}
      </ol>
      <button type="button" className="btn-secondary onboarding-guide__done" onClick={dismiss}>
        Got it, hide this guide
      </button>
    </div>
  )
}
