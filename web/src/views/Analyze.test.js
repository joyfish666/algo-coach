import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const apiMocks = {
  analyze: vi.fn(),
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

import Analyze from './Analyze.vue'

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
    apiMocks.importSite = vi.fn().mockResolvedValue({ imported: 3, skipped: 0 })

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

  it('offers a regenerate action once a report is rendered', async () => {
    // report presence used to be the sole toggle for the generate button:
    // after importing new submissions there was no way to refresh the report
    // without a full page reload
    apiMocks.analyze.mockResolvedValue({
      stats: { solved_total: 1, by_difficulty: { easy: 1, medium: 0, hard: 0 } },
      tags: [],
      recommendations: [],
      ai_report: '**第一版报告**',
      ai_configured: true,
    })
    const wrapper = mount(Analyze, {
      global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot/></a>' } } },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="generate-report"]').exists()).toBe(false)

    apiMocks.analyze.mockResolvedValueOnce({
      stats: { solved_total: 2, by_difficulty: { easy: 2, medium: 0, hard: 0 } },
      tags: [],
      recommendations: [],
      ai_report: '**第二版报告**',
      ai_configured: true,
    })
    await wrapper.find('[data-testid="regenerate-report"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ai-report"]').html()).toContain('第二版报告')
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
