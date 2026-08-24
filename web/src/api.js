import { debugEnabled, debugLog } from './debug'
import { useI18nStore } from './stores/i18n'

// Every fetch gets an abort deadline: without one, a hung backend (TCP
// established, response never arriving) freezes the calling view forever.
// The caps sit comfortably above the backend's own ceilings (LLM 120s,
// submit polling 120s) so the frontend never aborts a healthy call first.
const DEFAULT_TIMEOUT_MS = 45000

function timeoutSignal(timeoutMs) {
  if (!timeoutMs || typeof AbortSignal === 'undefined' || !AbortSignal.timeout) {
    return undefined // older browsers: degrade to no timeout instead of breaking
  }
  return AbortSignal.timeout(timeoutMs)
}

function translateMessageKey(key) {
  if (!key) return null
  try {
    const translated = useI18nStore().t(key)
    // an untranslated key echoes itself; keep the raw server text as fallback
    return translated !== key ? translated : null
  } catch {
    return null
  }
}

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
    // single point where server error payloads become user-visible text:
    // prefer the localized message_key so wording follows the UI language
    // instead of the backend process locale
    const message =
      translateMessageKey(payload?.error?.message_key) ||
      (payload && payload.error && payload.error.message) ||
      (typeof payload?.detail === 'string' ? payload.detail : null) ||
      `HTTP ${response.status}`
    if (debugEnabled.value) {
      debugLog(
        'http',
        `${response.status} ${response.url} -> ${JSON.stringify(payload).slice(0, 400)}`
      )
    }
    const error = new Error(message)
    error.status = response.status
    error.payload = payload
    throw error
  }
  return response.json()
}

async function request(url, options = {}) {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options
  const signal = timeoutSignal(timeoutMs)
  if (signal) {
    fetchOptions.signal = signal
  }
  try {
    return await fetch(url, fetchOptions).then(handle)
  } catch (err) {
    if (err instanceof DOMException && (err.name === 'TimeoutError' || err.name === 'AbortError')) {
      const i18n = useI18nStore()
      throw new Error(i18n.t('request_timeout'), { cause: err })
    }
    throw err
  }
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
  getProblem: (qid) =>
    request(`/api/problem/${encodeURIComponent(qid)}`, { timeoutMs: 60000 }),
  getTemplate: (qid, lang) =>
    request(`/api/problem/${encodeURIComponent(qid)}/template?lang=${encodeURIComponent(lang)}`, {
      timeoutMs: 60000,
    }),
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
      timeoutMs: 90000,
    }),
  judgeSubmit: (body) =>
    request('/api/judge/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      timeoutMs: 150000,
    }),
  analyze: (body = { use_llm: false }) =>
    request('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      timeoutMs: 150000,
    }),
  ask: (body) =>
    request('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      timeoutMs: 150000,
    }),
  importSite: (limit = 20) =>
    request('/api/archive/import-site', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ limit }),
      timeoutMs: 120000,
    }),
  archiveRecent: ({ limit = 50, qid } = {}) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (qid) params.set('qid', qid)
    return request(`/api/archive/recent?${params.toString()}`)
  },
  putNotes: (qid, content) =>
    request(`/api/problem/${encodeURIComponent(qid)}/notes`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    }),
  putFavorite: (qid, favorite) =>
    request(`/api/problem/${encodeURIComponent(qid)}/favorite`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ favorite }),
    }),
  clearLocalData: () => request('/api/local-data', { method: 'DELETE' }),
}
