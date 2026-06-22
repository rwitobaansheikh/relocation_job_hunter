import { Link, useLocation } from 'react-router-dom'
import { useJobSearch } from '../JobSearchContext'
import JobSearchProgress from './JobSearchProgress'

export default function GlobalJobSearchStatus() {
  const { searching, stopping, progress, stopSearch, statusMessage, results } = useJobSearch()
  const location = useLocation()
  const onJobsPage = location.pathname === '/app/jobs'

  if (!searching && !progress) return null

  return (
    <div className="global-job-search-status">
      <JobSearchProgress
        progress={progress}
        onStop={stopSearch}
        stopping={stopping}
        running={searching}
      />
      {!searching && statusMessage && !onJobsPage && (
        <div className={`alert alert-${statusMessage.type}`} style={{ marginTop: '0.75rem' }}>
          {statusMessage.text}
          {results?.jobs_stored > 0 && (
            <>
              {' '}
              <Link to="/app/applications">View Applications →</Link>
            </>
          )}
        </div>
      )}
    </div>
  )
}
