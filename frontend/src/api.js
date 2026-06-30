const API_BASE = '/api'

const TOKEN_KEY = 'jh_token'
let authToken = localStorage.getItem(TOKEN_KEY) || null

export function setToken(token) {
  authToken = token || null
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function getToken() {
  return authToken
}

async function request(path, options = {}) {
  const isForm = options.body instanceof FormData
  const headers = { ...options.headers }
  if (!isForm) headers['Content-Type'] = 'application/json'
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (res.status === 401) {
    setToken(null)
    // Let the auth layer react (clear user, redirect to login).
    window.dispatchEvent(new Event('auth:unauthorized'))
  }
  if (res.status === 402) {
    const err = await res.json().catch(() => ({ detail: 'Plan upgrade required' }))
    window.dispatchEvent(new CustomEvent('plan:upgrade_required', { detail: { message: err.detail } }))
    throw new Error(err.detail || 'Plan upgrade required')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  if (res.status === 204) return null
  return res.json()
}

function upload(path, file) {
  const form = new FormData()
  form.append('file', file)
  return request(path, { method: 'POST', body: form })
}

export const api = {
  // --- Auth ---
  register: (data) => request('/auth/register', { method: 'POST', body: JSON.stringify(data) }),
  login: (data) => request('/auth/login', { method: 'POST', body: JSON.stringify(data) }),
  me: () => request('/auth/me'),
  changePassword: (data) => request('/auth/change-password', { method: 'POST', body: JSON.stringify(data) }),
  getGoogleAuthUrl: () => request('/auth/google/url'),
  getLinkedinAuthUrl: () => request('/auth/linkedin/url'),
  getOAuthStatus: () => request('/auth/oauth/status'),
  deleteAccount: (password) =>
    request('/account', { method: 'DELETE', body: JSON.stringify({ password, confirm: 'DELETE' }) }),

  // --- Profile (current user) ---
  getProfile: () => request('/profile'),
  updateProfile: (data) => request('/profile', { method: 'PATCH', body: JSON.stringify(data) }),
  uploadCV: (file) => upload('/profile/upload-cv', file),
  uploadCoverLetter: (file) => upload('/profile/upload-cover-letter', file),
  suggestRoles: () => request('/profile/suggest-roles', { method: 'POST' }),
  suggestSearchCriteria: () => request('/profile/suggest-search-criteria', { method: 'POST' }),

  // --- Settings ---
  getSettings: () => request('/settings'),
  updateSettings: (data) => request('/settings', { method: 'PATCH', body: JSON.stringify(data) }),

  // --- Jobs ---
  searchJobs: (payload = {}) =>
    request('/jobs/search', {
      method: 'POST',
      body: JSON.stringify({ max_jobs: 100, ...payload }),
    }),

  streamSearchJobs: async (payload, onEvent, options = {}) => {
    const headers = { 'Content-Type': 'application/json' }
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`

    const response = await fetch(`${API_BASE}/jobs/search`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ max_jobs: 100, ...payload }),
      signal: options.signal,
    })

    if (!response.ok) {
      const text = await response.text()
      let msg = text
      try { msg = JSON.parse(text).detail || text } catch (e) {}
      throw new Error(msg)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    try {
      while (true) {
        if (options.signal?.aborted) {
          await reader.cancel()
          break
        }

        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              onEvent(data)
              if (data.type === 'cancelled' || data.type === 'done') {
                return data
              }
            } catch (e) {
              console.error('Failed to parse SSE JSON:', line)
            }
          }
        }
      }
    } catch (err) {
      if (options.signal?.aborted || err.name === 'AbortError') {
        return { type: 'cancelled' }
      }
      throw err
    }
    return null
  },

  importJob: (url) =>
    request('/jobs/import', { method: 'POST', body: JSON.stringify({ url }) }),

  addManualJob: (payload) =>
    request('/jobs/manual', { method: 'POST', body: JSON.stringify(payload) }),

  // --- Applications ---
  getApplications: (status, sort, options = {}) => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (sort) params.set('sort', sort)
    if (options.automationBatch) params.set('automation_batch', options.automationBatch)
    if (options.manualOnly) params.set('manual_only', 'true')
    const qs = params.toString()
    return request(`/applications${qs ? `?${qs}` : ''}`)
  },
  getAutomationBatches: () => request('/applications/automation-batches'),
  getTailoredDocuments: (applicationId) => request(`/applications/${applicationId}/documents`),
  updateCoverLetter: (applicationId, text) =>
    request(`/applications/${applicationId}/cover-letter`, {
      method: 'PATCH',
      body: JSON.stringify({ text }),
    }),
  fetchTailoredDocument: async (applicationId, docType) => {
    const headers = {}
    if (authToken) headers['Authorization'] = `Bearer ${authToken}`
    const res = await fetch(`${API_BASE}/applications/${applicationId}/documents/${docType}`, { headers })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || 'Failed to load document')
    }
    return res.blob()
  },
  deleteAllApplications: () => request('/applications', { method: 'DELETE' }),
  deleteApplication: (applicationId) =>
    request(`/applications/${applicationId}`, { method: 'DELETE' }),
  tailorDocuments: (applicationIds) =>
    request('/applications/tailor', { method: 'POST', body: JSON.stringify({ application_ids: applicationIds }) }),
  tailorSingle: (applicationId) =>
    request(`/applications/${applicationId}/tailor`, { method: 'POST' }),
  generateOutreachDraft: (applicationId) =>
    request(`/applications/${applicationId}/outreach-draft`, { method: 'POST' }),
  scheduleFollowUp: (applicationId, notes, scheduleNextDays = 7) =>
    request('/applications/follow-up', {
      method: 'POST',
      body: JSON.stringify({ application_id: applicationId, notes, schedule_next_days: scheduleNextDays }),
    }),
  updateStatus: (applicationId, status) =>
    request(`/applications/${applicationId}/status?status=${status}`, { method: 'PATCH' }),
  getDashboardStats: () => request('/dashboard/stats'),
  getAutomationRuns: () => request('/automation/runs'),

  // --- Automation loops ---
  getLoops: () => request('/automation/loops'),
  createLoop: (data) => request('/automation/loops', { method: 'POST', body: JSON.stringify(data) }),
  updateLoop: (loopId, data) =>
    request(`/automation/loops/${loopId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteLoop: (loopId) => request(`/automation/loops/${loopId}`, { method: 'DELETE' }),

  // --- Billing ---
  getBilling: (sessionId) => {
    const url = sessionId 
      ? `/billing?session_id=${encodeURIComponent(sessionId)}` 
      : `/billing?_t=${Date.now()}`
    return request(url)
  },
  syncBilling: () => request('/billing/sync', { method: 'POST' }),
  checkout: (tier) => request('/billing/checkout', { method: 'POST', body: JSON.stringify({ tier }) }),
  startTrialCheckout: () => request('/billing/trial-checkout', { method: 'POST' }),
  openPortal: () => request('/billing/portal', { method: 'POST' }),

  // --- Feedback / reviews / contact (public) ---
  getReviews: () => request('/reviews'),
  submitReview: (data) => request('/reviews', { method: 'POST', body: JSON.stringify(data) }),
  submitContact: (data) => request('/contact', { method: 'POST', body: JSON.stringify(data) }),

  // --- Admin ---
  getUsers: () => request('/admin/users'),
  updateUser: (userId, data) => request(`/admin/users/${userId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  getAdminStats: () => request('/admin/stats'),
  setKillSwitch: (enabled) =>
    request('/admin/automation/kill-switch', { method: 'POST', body: JSON.stringify({ enabled }) }),
  getFeedback: (kind) => request(`/admin/feedback${kind ? `?kind=${kind}` : ''}`),
  updateFeedback: (id, data) =>
    request(`/admin/feedback/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteFeedback: (id) => request(`/admin/feedback/${id}`, { method: 'DELETE' }),
}

export const CONTACT_EMAIL = 'rwitobaansheikh@gmail.com'
