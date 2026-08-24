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

  it('falls back to HTTP status text without an error payload', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(errorResponse(500, null)))
    const err = await api.getStatus().catch((e) => e)
    expect(err.message).toBe('HTTP 500')
  })

  it('passes through successful bodies untouched', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse({ app: 'algocoach' })))
    await expect(api.getStatus()).resolves.toEqual({ app: 'algocoach' })
  })
})
