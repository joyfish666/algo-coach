import { createPinia, setActivePinia } from 'pinia'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

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
    apiMocks.getStatus.mockResolvedValue({ configured: false, sync: {} })
    await router.push('/settings')
    expect(router.currentRoute.value.path).toBe('/setup')
  })
})
