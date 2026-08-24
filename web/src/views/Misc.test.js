import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const apiMocks = {
  getDaily: vi.fn(),
  analyze: vi.fn(),
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

import Daily from './Daily.vue'
import Analyze from './Analyze.vue'
import Settings from './Settings.vue'

describe('Daily view', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiMocks.getDaily.mockReset()
    localStorage.clear()
  })

  it('renders the daily problem and navigates to its workbench', async () => {
    apiMocks.getDaily.mockResolvedValue({
      slug: 'daily-2026',
      frontend_id: '42',
      title_cn: '接雨水',
      difficulty: 'hard',
      tags: [],
    })
    const wrapper = mount(Daily, {
      global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot/></a>' } } },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="daily-card"]').text()).toContain('接雨水')

    await wrapper.find('[data-testid="open-workbench"]').trigger('click')
    expect(pushSpy).toHaveBeenCalledWith('/problem/daily-2026')
  })

  it('shows an explicit empty state when the site returns nothing', async () => {
    apiMocks.getDaily.mockResolvedValue(null)
    const wrapper = mount(Daily, {
      global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot/></a>' } } },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="daily-empty"]').exists()).toBe(true)
  })
})

describe('Analyze view', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiMocks.analyze.mockReset()
    localStorage.clear()
  })

  it('renders stat cards and colored recommendation difficulty chips', async () => {
    apiMocks.analyze.mockResolvedValue({
      stats: {
        solved_total: 3,
        by_difficulty: { easy: 2, medium: 1, hard: 0 },
        attempts_total: 9,
      },
      tags: [],
      recommendations: [
        { slug: 'rec-hard', frontend_id: '76', title_cn: '最小覆盖子串', difficulty: 'hard' },
      ],
      ai_report: null,
      ai_configured: false,
    })
    const wrapper = mount(Analyze, {
      global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot/></a>' } } },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('3')
    expect(wrapper.find('.chip-hard').exists()).toBe(true)
  })
})

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
})
