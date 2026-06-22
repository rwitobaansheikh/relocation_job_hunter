import { useEffect, useState } from 'react'
import HelpButton from './HelpButton'

function formatElapsed(ms) {
  const totalSec = Math.floor(ms / 1000)
  const min = Math.floor(totalSec / 60)
  const sec = totalSec % 60
  if (min > 0) return `${min}m ${sec}s`
  return `${sec}s`
}

export default function JobSearchProgress({ progress, onStop, stopping, running = true }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!progress?.startedAt || !running) return undefined
    const tick = () => setElapsed(Date.now() - progress.startedAt)
    tick()
    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [progress?.startedAt, running])

  if (!progress) return null

  const stats = progress.stats || {}

  return (
    <div className={`card job-search-progress${running ? '' : ' job-search-progress--done'}`} role="status" aria-live="polite">
      <div className="job-search-progress__header">
        {running ? (
          <div className="job-search-progress__spinner" aria-hidden="true" />
        ) : (
          <div className="job-search-progress__done-icon" aria-hidden="true">✓</div>
        )}
        <div className="job-search-progress__headline">
          <strong>{running ? 'Search in progress' : 'Search finished'}</strong>
          {(running || progress.startedAt) && (
            <span className="muted job-search-progress__elapsed">{formatElapsed(elapsed)}</span>
          )}
        </div>
        {running && (
          <HelpButton
            className="btn-secondary btn-sm"
            onClick={onStop}
            disabled={stopping}
            title="Stop search"
            help="Stops the current job search. Jobs already saved stay in Applications."
          >
            {stopping ? 'Stopping…' : 'Stop search'}
          </HelpButton>
        )}
      </div>

      <p className="job-search-progress__message">{progress.message || 'Searching for matching roles…'}</p>

      {(progress.role || progress.location || progress.page) && (
        <div className="job-search-progress__meta muted">
          {progress.role ? <span>Role: {progress.role}</span> : null}
          {progress.location ? <span>Location: {progress.location || 'worldwide'}</span> : null}
          {progress.page ? <span>Page: {progress.page}</span> : null}
        </div>
      )}

      <div className="job-search-progress__stats">
        <div><strong>{stats.jobs_found ?? 0}</strong><span className="muted"> matched</span></div>
        <div><strong>{stats.jobs_stored ?? 0}</strong><span className="muted"> saved</span></div>
        <div><strong>{stats.jobs_filtered ?? 0}</strong><span className="muted"> filtered out</span></div>
      </div>

      {progress.recentJobs?.length > 0 && (
        <div className="job-search-progress__recent">
          <div className="job-search-progress__recent-label">Latest matches</div>
          <ul>
            {progress.recentJobs.map((job, i) => (
              <li key={`${job.url || job.title}-${i}`}>
                <strong>{job.title}</strong>
                <span className="muted">
                  {' · '}{job.company}{job.location ? ` · ${job.location}` : ''}
                  {job.match_score > 0 ? ` · Match ${job.match_score}/100` : ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
