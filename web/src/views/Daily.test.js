import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const apiMocks = {
  getDaily: vi.fn(),
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
