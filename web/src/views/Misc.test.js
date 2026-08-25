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

  it('keeps a generated AI report when the stats reload without one', async () => {
    apiMocks.analyze
      .mockResolvedValueOnce({
        stats: { solved_total: 1, by_difficulty: { easy: 1, medium: 0, hard: 0 } },
        tags: [],
        recommendations: [],
        ai_report: '**重点练习链表**',
        ai_configured: true,
      })
      .mockResolvedValue({
        stats: { solved_total: 2, by_difficulty: { easy: 2, medium: 0, hard: 0 } },
        tags: [],
        recommendations: [],
        ai_report: null, // plain refreshes never carry a report
        ai_configured: true,
      })
    const importMock = vi.fn().mockResolvedValue({ imported: 3, skipped: 0 })
    apiMocks.importSite = importMock

    const wrapper = mount(Analyze, {
      global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot/></a>' } } },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="ai-report"]').exists()).toBe(true)

    // an import finished and triggered a stats reload
    await wrapper.find('[data-testid="import-btn"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ai-report"]').exists()).toBe(true)
  })

  it('surfaces a failed AI generation inline instead of tearing down the page', async () => {
    apiMocks.analyze
      .mockResolvedValueOnce({
        stats: { solved_total: 1, by_difficulty: { easy: 0, medium: 1, hard: 0 } },
        tags: [],
        recommendations: [],
        ai_report: null,
        ai_configured: true,
      })
      .mockRejectedValueOnce(new Error('LLM upstream 502'))

    const wrapper = mount(Analyze, {
      global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot/></a>' } } },
    })
    await flushPromises()

    await wrapper.find('[data-testid="generate-report"]').trigger('click')
    await flushPromises()
    // statistics stay visible; only the action reports its failure
    expect(wrapper.text()).toContain('1')
    expect(wrapper.find('[data-testid="ai-action-error"]').text()).toContain('LLM upstream 502')
    expect(wrapper.find('.empty-state').exists()).toBe(false)
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
