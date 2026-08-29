import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const apiMocks = {
  getSettings: vi.fn(),
  putSettings: vi.fn().mockResolvedValue({}),
}

vi.mock('../api', () => ({
  api: new Proxy({}, {
    get: (_t, prop) => apiMocks[prop] ?? vi.fn(),
  }),
}))

const pushSpy = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushSpy }),
  RouterLink: { template: '<a><slot/></a>' },
}))

import Settings from './Settings.vue'

describe('Settings view', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiMocks.getSettings.mockReset()
    localStorage.clear()
    document.documentElement.dataset.theme = ''
  })

  it('loads current settings and marks cookie state', async () => {
    apiMocks.getSettings.mockResolvedValue({ default_language: 'python3', configured: true })
    const wrapper = mount(Settings, {
      global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot/></a>' } } },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="coding-lang-select"]').element.value).toBe('python3')
    expect(wrapper.find('[data-testid="cookie-chip"]').classes()).toContain('chip-ok')
  })

  it('keeps the destructive erase button disabled until DELETE is typed', async () => {
    apiMocks.getSettings.mockResolvedValue({ default_language: 'cpp', configured: false })
    const wrapper = mount(Settings, {
      global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot/></a>' } } },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="clear-data-btn"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-testid="clear-confirm-input"]').setValue('delete ')
    expect(wrapper.find('[data-testid="clear-data-btn"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-testid="clear-confirm-input"]').setValue('DELETE')
    expect(wrapper.find('[data-testid="clear-data-btn"]').attributes('disabled')).toBeUndefined()
  })

  it('saves the default coding language', async () => {
    apiMocks.getSettings.mockResolvedValue({ default_language: 'cpp', configured: true })
    const wrapper = mount(Settings, {
      global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot/></a>' } } },
    })
    await flushPromises()
    await wrapper.find('[data-testid="coding-lang-select"]').setValue('java')
    await wrapper.findAll('button').find((b) => b.text() === 'Save').trigger('click')
    expect(apiMocks.putSettings).toHaveBeenCalledWith({ default_language: 'java' })
    expect(wrapper.find('[data-testid="saved-hint"]').exists()).toBe(true)
  })

  it('purges browser-side code drafts when all data is erased', async () => {
    // drafts live in localStorage, outside the backend data dir: a wipe that
    // only hit the server would resurface pre-erase code via the restore bar
    apiMocks.getSettings.mockResolvedValue({ default_language: 'cpp', configured: true })
    const clearMock = vi.fn().mockResolvedValue({ cleared: ['config.toml'] })
    apiMocks.clearLocalData = clearMock
    localStorage.setItem('algocoach-snapshot:two-sum::cpp', JSON.stringify({ c: '// old', t: 1 }))
    localStorage.setItem('algocoach-snapshot-index', '[]')
    localStorage.setItem('algocoach-theme', 'dark') // preference, must survive

    const wrapper = mount(Settings, {
      global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot/></a>' } } },
    })
    await flushPromises()
    await wrapper.find('[data-testid="clear-confirm-input"]').setValue('DELETE')
    await wrapper.find('[data-testid="clear-data-btn"]').trigger('click')
    await flushPromises()

    expect(clearMock).toHaveBeenCalled()
    expect(localStorage.getItem('algocoach-snapshot:two-sum::cpp')).toBeNull()
    expect(localStorage.getItem('algocoach-snapshot-index')).toBeNull()
    expect(localStorage.getItem('algocoach-theme')).toBe('dark')
  })
})
