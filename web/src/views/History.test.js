import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const apiMocks = {
  archiveRecent: vi.fn(),
}

vi.mock('../api', () => ({
  api: new Proxy({}, {
    get: (_t, prop) => apiMocks[prop] ?? vi.fn(),
  }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import History from './History.vue'

const RECORDS = [
  {
    timestamp: '2026-08-24T02:00:00+00:00',
    slug: 'two-sum',
    frontend_id: '1',
    lang: 'cpp',
    status: 'accepted',
    runtime_display: '52 ms',
    memory_display: '41 MB',
  },
  {
    timestamp: '2026-08-23T10:00:00+00:00',
    slug: 'add-two-numbers',
    frontend_id: '2',
    lang: 'python3',
    status: 'wrong_answer',
    runtime_display: '',
    memory_display: '',
    outputs: ['[7,0,8]'],
    expected_outputs: ['[7,0,9]'],
  },
]

async function mountHistory() {
  const wrapper = mount(History, {
    global: {
      plugins: [createPinia()],
      stubs: { RouterLink: { template: '<a><slot/></a>' } },
    },
  })
  await flushPromises()
  return wrapper
}

describe('History view', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiMocks.archiveRecent.mockReset()
    localStorage.clear()
  })

  it('lists archived submissions newest first with verdict chips', async () => {
    apiMocks.archiveRecent.mockResolvedValue({ records: RECORDS })
    const wrapper = await mountHistory()
    // top-level rows only; the expandable WA detail nests its own table
    const rows = wrapper.findAll('[data-testid="history-table"] > tbody > tr')
    expect(rows).toHaveLength(2)
    expect(wrapper.text()).toContain('accepted')
    expect(wrapper.text()).toContain('wrong_answer')
    expect(wrapper.text()).toContain('52 ms')
    expect(apiMocks.archiveRecent).toHaveBeenCalledWith({ limit: 100, qid: undefined })
  })

  it('passes the qid filter to the API', async () => {
    apiMocks.archiveRecent.mockResolvedValue({ records: [] })
    const wrapper = await mountHistory()
    await wrapper.find('[data-testid="history-qid-input"]').setValue('two-sum')
    await wrapper.find('[data-testid="history-apply"]').trigger('click')
    expect(apiMocks.archiveRecent).toHaveBeenLastCalledWith({ limit: 100, qid: 'two-sum' })
  })

  it('shows an explicit empty state when nothing is archived yet', async () => {
    apiMocks.archiveRecent.mockResolvedValue({ records: [] })
    const wrapper = await mountHistory()
    expect(wrapper.find('[data-testid="history-empty"]').exists()).toBe(true)
  })

  it('exposes failing outputs in an expandable detail', async () => {
    apiMocks.archiveRecent.mockResolvedValue({ records: RECORDS })
    const wrapper = await mountHistory()
    const html = wrapper.find('[data-testid="history-table-card"]').html()
    expect(html).toContain('[7,0,8]')
    expect(html).toContain('[7,0,9]')
  })
})
