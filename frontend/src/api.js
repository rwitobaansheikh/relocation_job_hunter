const API_BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

export const api = {
  createProfile: (data) => request('/profiles', { method: 'POST', body: JSON.stringify(data) }),
  getProfiles: () => request('/profiles'),
  getProfile: (id) => request(`/profiles/${id}`),
  updateProfile: (id, data) => request(`/profiles/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

  uploadCV: async (profileId, file) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${API_BASE}/profiles/${profileId}/upload-cv`, { method: 'POST', body: form })
    if (!res.ok) throw new Error('CV upload failed')
    return res.json()
  },

  uploadCoverLetter: async (profileId, file) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${API_BASE}/profiles/${profileId}/upload-cover-letter`, { method: 'POST', body: form })
    if (!res.ok) throw new Error('Cover letter upload failed')
    return res.json()
  },

  searchJobs: (userProfileId, maxJobs = 100) =>
    request('/jobs/search', { method: 'POST', body: JSON.stringify({ user_profile_id: userProfileId, max_jobs: maxJobs }) }),

  getApplications: (profileId, status) => {
    const params = new URLSearchParams()
    if (profileId) params.set('profile_id', profileId)
    if (status) params.set('status', status)
    return request(`/applications?${params}`)
  },

  deleteAllApplications: (profileId) =>
    request(`/applications?profile_id=${profileId}`, { method: 'DELETE' }),

  tailorDocuments: (applicationIds) =>
    request('/applications/tailor', { method: 'POST', body: JSON.stringify({ application_ids: applicationIds }) }),

  tailorSingle: (applicationId) =>
    request(`/applications/${applicationId}/tailor`, { method: 'POST' }),

  sendOutreach: (applicationId, dryRun = false, testToSelf = false) =>
    request('/applications/send-outreach', {
      method: 'POST',
      body: JSON.stringify({ application_id: applicationId, dry_run: dryRun, test_to_self: testToSelf }),
    }),

  scheduleFollowUp: (applicationId, notes, scheduleNextDays = 7) =>
    request('/applications/follow-up', {
      method: 'POST',
      body: JSON.stringify({ application_id: applicationId, notes, schedule_next_days: scheduleNextDays }),
    }),

  updateStatus: (applicationId, status) =>
    request(`/applications/${applicationId}/status?status=${status}`, { method: 'PATCH' }),

  getDashboardStats: (profileId) => request(`/dashboard/stats?profile_id=${profileId}`),

  getOutreachEmails: (applicationId) => request(`/applications/${applicationId}/emails`),

  getContacts: (applicationId) => request(`/applications/${applicationId}/contacts`),
}
