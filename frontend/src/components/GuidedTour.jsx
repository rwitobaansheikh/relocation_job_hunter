export const TOUR_STEPS = [
  {
    target: '/app',
    title: 'Welcome to your dashboard',
    body: 'This is home base — track jobs discovered, tailored, and applied at a glance.',
  },
  {
    target: '/app/profile',
    title: 'Step 1 — Add your documents',
    body: 'Upload your CV and cover letter here first. Every other feature — search, tailoring, matching — uses these.',
  },
  {
    target: '/app/jobs',
    title: 'Step 2 — Search for jobs',
    body: 'Set your filters and run a search. Matches save to Applications automatically.',
  },
  {
    target: '/app/applications',
    title: 'Step 3 — Tailor & apply',
    body: 'Generate a tailored CV and cover letter for each job, download them, then apply on the job site.',
  },
]

export const TOUR_SEEN_KEY = 'jaf_tour_seen'

export default function GuidedTour({ step, onNext, onSkip }) {
  const data = TOUR_STEPS[step]
  if (!data) return null
  const isLast = step === TOUR_STEPS.length - 1

  return (
    <div aria-live="polite" className="tour-card">
      <div className="tour-card__step">
        Step {step + 1} of {TOUR_STEPS.length}
      </div>
      <h3>{data.title}</h3>
      <p>{data.body}</p>
      <div className="actions">
        <button type="button" className="tour-skip" onClick={onSkip}>
          Skip tour
        </button>
        <button type="button" className="btn-primary" onClick={onNext}>
          {isLast ? 'Finish' : 'Next'}
        </button>
      </div>
    </div>
  )
}
