import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from './api'
import { useI18nStore } from './stores/i18n'

function okResponse(body) {
  return { ok: true, json: () => Promise.resolve(body) }
}

function errorResponse(status, payload) {
  return {
    ok: false,
    status,
    url: '/api/x',
    json: () => Promise.resolve(payload),
  }
}

describe('api error translation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('translates a known message_key into the UI language', async () => {
    useI18nStore().set('zh')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        errorResponse(401, {
          error: { kind: 'AuthError', message_key: 'cookie_invalid', message: 'Cookie 已失效' },
        })
      )
    )
    const err = await api.getStatus().catch((e) => e)
    expect(err.message).toBe('Cookie 已失效，请重新粘贴')
  })

  it('keeps the server message when the key is unknown to the catalog', async () => {
    useI18nStore().set('zh')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        errorResponse(400, {
          error: { kind: 'WeirdError', message_key: 'not_in_catalog', message: 'raw text' },
        })
      )
    )
    const err = await api.getStatus().catch((e) => e)
    expect(err.message).toBe('raw text')
  })

  it('translates message_key carried in structured HTTPException details', async () => {
    // HTTPException sites (sync conflict, ask-not-configured, 404s) used to
    // ship backend-locale text with no key; the frontend must translate them
    // like domain errors
    useI18nStore().set('zh')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        errorResponse(409, {
          detail: { kind: 'HTTPException', message_key: 'sync_in_progress', message: '题库同步正在进行中' },
        })
      )
    )
    const err = await api.startSync().catch((e) => e)
    expect(err.message).toBe('题库同步正在进行中')
  })

  it('maps network-level failures to a localized message instead of raw browser text', async () => {
    useI18nStore().set('zh')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const err = await api.getStatus().catch((e) => e)
    expect(err.message).toBe('无法连接本地服务：请确认 coach 进程仍在运行')
    expect(err.message).not.toContain('Failed to fetch')
  })

  it('falls back to HTTP status text without an error payload', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(errorResponse(500, null)))
    const err = await api.getStatus().catch((e) => e)
    expect(err.message).toBe('HTTP 500')
  })

  it('passes through successful bodies untouched', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse({ app: 'algocoach' })))
    await expect(api.getStatus()).resolves.toEqual({ app: 'algocoach' })
  })

  it('attaches the UI language to ask and analyze payloads', async () => {
    // the backend phrases the coach prompt and report digest in this
    // language; without it the coach always replied in Chinese
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    useI18nStore().set('en')
    await api.ask({ question: 'why?' })
    await api.analyze({ use_llm: true })
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).ui_lang).toBe('en')
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).ui_lang).toBe('en')
  })
})
