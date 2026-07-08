import { createContext, useCallback, useContext, useRef, useState } from 'react'
import { api } from './api'

const JobSearchContext = createContext(null)

export function JobSearchProvider({ children }) {
  const [searching, setSearching] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [progress, setProgress] = useState(null)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  const [statusMessage, setStatusMessage] = useState(null)
  const abortRef = useRef(null)
  const activeRef = useRef(false)

  const stopSearch = useCallback(() => {
    if (!abortRef.current) return
    setStopping(true)
    abortRef.current.abort()
  }, [])

  const startSearch = useCallback(async (filters) => {
    if (activeRef.current) return

    activeRef.current = true
    const controller = new AbortController()
    abortRef.current = controller
    setSearching(true)
    setStopping(false)
    setError(null)
    setResults(null)
    setStatusMessage(null)

    const startedAt = Date.now()
    let sessionTotals = { jobs_found: 0, jobs_stored: 0, jobs_filtered: 0 }
    let recentJobs = []

    const updateProgress = (patch) => {
      setProgress((prev) => ({
        startedAt,
        message: patch.message ?? prev?.message ?? 'Searching…',
        role: patch.role ?? prev?.role,
        location: patch.location ?? prev?.location,
        page: patch.page ?? prev?.page,
        stats: patch.stats ?? prev?.stats ?? sessionTotals,
        recentJobs: patch.recentJobs ?? prev?.recentJobs ?? recentJobs,
      }))
    }

    updateProgress({
      message: 'Preparing search…',
      stats: { jobs_found: 0, jobs_stored: 0, jobs_filtered: 0 },
      recentJobs: [],
    })

    try {
      const locList = (filters.locations || '')
        .split(',')
        .map((l) => l.trim())
        .filter(Boolean)
      if (locList.length === 0) locList.push('')

      let stopped = false

      for (const loc of locList) {
        if (controller.signal.aborted) {
          stopped = true
          break
        }

        const payload = {
          max_jobs: 100,
          seniority_levels: filters.seniority || [],
          posted_within_hours: Number(filters.postedWithin ?? 24),
          location: loc,
          work_types: filters.workTypes || [],
        }
        if (filters.searchRoles?.length) payload.roles = filters.searchRoles
        if (filters.minSalary) payload.min_salary = Number(filters.minSalary)
        if (filters.maxSalary) payload.max_salary = Number(filters.maxSalary)

        if (locList.length > 1) {
          updateProgress({
            message: `Searching location: ${loc || 'default profile locations'}…`,
            location: loc,
          })
        }

        const finalEvent = await api.streamSearchJobs(
          payload,
          (event) => {
            if (event.type === 'progress' || event.type === 'status') {
              updateProgress({
                message: event.message,
                role: event.role,
                location: event.location ?? loc,
                page: event.page,
                stats: {
                  jobs_found: sessionTotals.jobs_found + (event.stats?.jobs_found ?? 0),
                  jobs_stored: sessionTotals.jobs_stored + (event.stats?.jobs_stored ?? 0),
                  jobs_filtered: sessionTotals.jobs_filtered + (event.stats?.jobs_filtered ?? 0),
                },
              })
              return
            }

            if (event.type === 'job' && event.job) {
              recentJobs = [event.job, ...recentJobs.filter((j) => j.url !== event.job.url)].slice(0, 5)
              const liveStats = {
                jobs_found: sessionTotals.jobs_found + (event.stats?.jobs_found ?? 0),
                jobs_stored: sessionTotals.jobs_stored + (event.stats?.jobs_stored ?? 0),
                jobs_filtered: sessionTotals.jobs_filtered + (event.stats?.jobs_filtered ?? 0),
              }
              updateProgress({
                message: `Saved: ${event.job.title} at ${event.job.company}`,
                stats: liveStats,
                recentJobs,
              })
              setResults(liveStats)
              return
            }

            if (event.type === 'done' && event.stats) {
              sessionTotals = {
                jobs_found: sessionTotals.jobs_found + event.stats.jobs_found,
                jobs_stored: sessionTotals.jobs_stored + event.stats.jobs_stored,
                jobs_filtered: sessionTotals.jobs_filtered + event.stats.jobs_filtered,
              }
              updateProgress({
                message: event.message || 'Location search complete.',
                stats: sessionTotals,
              })
              setResults({ ...sessionTotals })
              return
            }

            if (event.type === 'cancelled') {
              updateProgress({
                message: event.message || 'Search stopped.',
                stats: event.stats || sessionTotals,
              })
            }

            if (event.type === 'error') {
              throw new Error(event.error || 'Search failed')
            }
          },
          { signal: controller.signal },
        )

        if (finalEvent?.type === 'cancelled' || controller.signal.aborted) {
          stopped = true
          break
        }
      }

      const totals = { ...sessionTotals }
      setResults(totals)
      if (stopped) {
        setStatusMessage({
          type: 'info',
          text: `Search stopped. ${totals.jobs_stored} job(s) saved to Applications.`,
        })
        updateProgress({
          message: `Search stopped — ${totals.jobs_stored} job(s) saved.`,
          stats: totals,
          recentJobs,
        })
      } else {
        setStatusMessage({
          type: 'success',
          text: `Search completed. ${totals.jobs_stored} job(s) saved — open Applications to review.`,
        })
        updateProgress({
          message: `Search complete — ${totals.jobs_stored} job(s) saved.`,
          stats: totals,
          recentJobs,
        })
      }
    } catch (err) {
      if (err.name === 'AbortError' || controller.signal.aborted) {
        setStatusMessage({ type: 'info', text: 'Search stopped.' })
      } else {
        setError(err.message)
        setProgress((prev) => ({
          ...prev,
          startedAt: prev?.startedAt || startedAt,
          message: err.message || 'Search failed.',
        }))
      }
    }

    setSearching(false)
    setStopping(false)
    abortRef.current = null
    activeRef.current = false
  }, [])

  const value = {
    searching,
    stopping,
    progress,
    results,
    error,
    statusMessage,
    startSearch,
    stopSearch,
    clearStatusMessage: () => setStatusMessage(null),
  }

  return <JobSearchContext.Provider value={value}>{children}</JobSearchContext.Provider>
}

export function useJobSearch() {
  const ctx = useContext(JobSearchContext)
  if (!ctx) {
    throw new Error('useJobSearch must be used within JobSearchProvider')
  }
  return ctx
}
