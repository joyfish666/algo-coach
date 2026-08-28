import { createPinia, setActivePinia } from 'pinia'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { useStatusStore } from './stores/status'

const apiMocks = {
  getStatus: vi.fn().mockResolvedValue({
    configured: true,
    version: '0.1.0',
    data_dir: '/tmp',
    sync: {},
  }),
}

vi.mock('./api', () => ({
  api: new Proxy({}, {
    get: (_t, prop) => apiMocks[prop] ?? vi.fn(),
  }),
}))

// view chunks pull heavy editors/monaco-free but still DOM-hungry libs;
// the smoke level asserts resolution + guards, per-view rendering is
// covered by the dedicated *.test.js files
vi.mock('./views/ProblemDetail.vue', () => ({ default: { template: '<div/>' } }))
vi.mock('./components/CodeEditor.vue', () => ({ default: { template: '<div/>' } }))

describe('router smoke', () => {
  let router

  beforeAll(async () => {
    setActivePinia(createPinia())
    const module = await import('./router')
    router = module.default
  })

  beforeEach(() => {
    apiMocks.getStatus.mockClear()
    apiMocks.getStatus.mockResolvedValue({
      configured: true,
      version: '0.1.0',
      data_dir: '/tmp',
      sync: {},
    })
  })

  const cases = [
    ['/problems', 'problems'],
    ['/daily', 'daily'],
    ['/history', 'history'],
    ['/analyze', 'analyze'],
    ['/settings', 'settings'],
    ['/setup', 'setup'],
    ['/problem/two-sum', 'problem-detail'],
  ]

  it.each(cases)('%s resolves to %s', async (path, name) => {
    await router.push(path)
    expect(router.currentRoute.value.name).toBe(name)
    // every lazily imported chunk actually resolved to a component
    expect(router.currentRoute.value.matched[0].components.default).toBeTruthy()
  })

  it('redirects / to the problem list', async () => {
    await router.push('/')
    expect(router.currentRoute.value.path).toBe('/problems')
  })

  it('redirects unknown paths to the problem list', async () => {
    await router.push('/nope/nope')
    expect(router.currentRoute.value.path).toBe('/problems')
  })

  it('forces /setup when no cookie is configured yet', async () => {
    // status is fetched fresh (stale store), as it would be right after
    // startup or a data-directory swap
    useStatusStore().$reset()
    apiMocks.getStatus.mockResolvedValue({ configured: false, sync: {} })
    await router.push('/settings')
    expect(router.currentRoute.value.path).toBe('/setup')
  })

  it('navigates on cached status inside the freshness window and revalidates in the background', async () => {
    useStatusStore().$reset()
    apiMocks.getStatus.mockResolvedValue({ configured: true, sync: {} })
    await router.push('/problems')
    const callsAfterWarmup = apiMocks.getStatus.mock.calls.length

    // backend flips to unconfigured, but the cached snapshot is fresh:
    // navigation must proceed instead of blocking on a round-trip (the real
    // redirect still happens via the setup flow refreshing its own status)
    apiMocks.getStatus.mockResolvedValue({ configured: false, sync: {} })
    await router.push('/daily')
    expect(router.currentRoute.value.path).toBe('/daily')
    // ...while one background refresh revalidated
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(apiMocks.getStatus.mock.calls.length).toBeGreaterThan(callsAfterWarmup)
  })
})
