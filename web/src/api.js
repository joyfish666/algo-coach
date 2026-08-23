async function handle(response) {
  if (!response.ok) {
    let payload = null
    try {
      payload = await response.json()
    } catch {
      /* non-json error body */
    }
    if (
      response.status === 401 &&
      payload && payload.error && payload.error.kind === 'AuthError'
    ) {
      window.dispatchEvent(
        new CustomEvent('algocoach:auth-expired', { detail: payload.error })
      )
    }
    const error = new Error(
      (payload && payload.error && payload.error.message) || `HTTP ${response.status}`
    )
    error.status = response.status
    error.payload = payload
    throw error
  }
  return response.json()
}

function request(url, options = {}) {
  return fetch(url, options).then(handle)
}

export const api = {
  getStatus: () => request('/api/status'),
  getSettings: () => request('/api/settings'),
  putSettings: (body) =>
    request('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  validateCookie: (cookie) =>
    request('/api/setup/validate-cookie', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cookie }),
    }),
  getProblems: () => request('/api/problems'),
  startSync: () =>
    request('/api/problems/sync', { method: 'POST' }),
  getSyncProgress: () => request('/api/problems/sync/progress'),
  getDaily: () => request('/api/daily'),
  getProblem: (qid) => request(`/api/problem/${encodeURIComponent(qid)}`),
  getTemplate: (qid, lang) =>
    request(`/api/problem/${encodeURIComponent(qid)}/template?lang=${encodeURIComponent(lang)}`),
  putTestcases: (qid, content) =>
    request(`/api/problem/${encodeURIComponent(qid)}/testcases`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    }),
  putSolution: (qid, lang, code) =>
    request(`/api/problem/${encodeURIComponent(qid)}/solution`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lang, code }),
    }),
  judgeRun: (body) =>
    request('/api/judge/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  judgeSubmit: (body) =>
    request('/api/judge/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
}
