import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const apiMocks = {
  getProblems: vi.fn(),
  putFavorite: vi.fn().mockResolvedValue({ slug: 'x', favorite: true }),
}

vi.mock('../api', () => ({
  api: new Proxy({}, {
    get: (_t, prop) => apiMocks[prop] ?? vi.fn(),
  }),
}))

const pushSpy = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/problems', fullPath: '/problems', query: {} }),
  useRouter: () => ({ push: pushSpy }),
}))

import Problems from './Problems.vue'
import { useI18nStore } from '../stores/i18n'
import { useToastStore } from '../stores/toast'

const ROWS = [
  {
    slug: 'two-sum',
    frontend_id: '1',
    title_cn: '两数之和',
    difficulty: 'easy',
    tags: [],
    practice_status: 'accepted',
  },
  {
    slug: 'add-two-numbers',
    frontend_id: '2',
    title_cn: '两数相加',
    difficulty: 'medium',
    tags: [],
    practice_status: 'wrong_answer',
  },
  {
    slug: 'longest-substring',
    frontend_id: '3',
    title_cn: '无重复字符最长子串',
    difficulty: 'medium',
    tags: [],
  },
]

async function mountProblems(rows = ROWS) {
  apiMocks.getProblems.mockResolvedValue({
    total: rows.length,
    synced_at: '2026-08-24T00:00:00+00:00',
    problems: JSON.parse(JSON.stringify(rows)),
  })
  // one pinia shared by the app and the test file, so store assertions read
  // the same instance the component pushes into
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(Problems, {
    global: {
      plugins: [pinia],
      stubs: {
        RouterLink: { template: '<a><slot/></a>' },
        Teleport: { template: '<div><slot/></div>' },
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('Problems view', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    apiMocks.getProblems.mockClear()
    apiMocks.putFavorite.mockClear()
    pushSpy.mockClear()
  })

  it('renders one card per problem row', async () => {
    const wrapper = await mountProblems()
    expect(wrapper.findAll('[data-testid="problem-card"]')).toHaveLength(3)
  })

  it('filters by practice status: solved / attempted / todo / favorite', async () => {
    const wrapper = await mountProblems()
    const select = wrapper.find('[data-testid="status-select"]')

    await select.setValue('solved')
    expect(wrapper.findAll('[data-testid="problem-card"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('两数之和')

    await select.setValue('attempted')
    expect(wrapper.findAll('[data-testid="problem-card"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('两数相加')

    await select.setValue('todo')
    expect(wrapper.findAll('[data-testid="problem-card"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('无重复字符最长子串')

    await select.setValue('favorite')
    expect(wrapper.find('[data-testid="no-match"]').exists()).toBe(true)

    await select.setValue('')
    expect(wrapper.findAll('[data-testid="problem-card"]')).toHaveLength(3)
  })

  it('toggling a favorite updates the card immediately and persists via API', async () => {
    const wrapper = await mountProblems()
    await wrapper.findAll('[data-testid="fav-toggle"]')[0].trigger('click')
    expect(apiMocks.putFavorite).toHaveBeenCalledWith('two-sum', true)
    expect(wrapper.vm.filtered.some((row) => row.favorite)).toBe(true)

    // the favorite filter now matches that row
    await wrapper.find('[data-testid="status-select"]').setValue('favorite')
    expect(wrapper.findAll('[data-testid="problem-card"]')).toHaveLength(1)
  })

  it('a failed favorite toggle rolls back the optimistic update', async () => {
    apiMocks.putFavorite.mockRejectedValueOnce(new Error('offline'))
    const wrapper = await mountProblems()
    await wrapper.findAll('[data-testid="fav-toggle"]')[0].trigger('click')
    expect(wrapper.vm.filtered.every((row) => !row.favorite)).toBe(true)
  })

  it('random button navigates to one of the filtered problems', async () => {
    const wrapper = await mountProblems()
    await wrapper.find('[data-testid="random-btn"]').trigger('click')
    expect(pushSpy).toHaveBeenCalledTimes(1)
    const target = pushSpy.mock.calls[0][0]
    expect(target).toMatch(/^\/problem\//)
    const slugs = ['two-sum', 'add-two-numbers', 'longest-substring']
    expect(slugs.some((slug) => target.endsWith(slug))).toBe(true)
  })

  it('random pick skips paid problems and explains when only paid remain', async () => {
    const paidOnly = ROWS.map((row) => ({ ...row, paid_only: true }))
    const wrapper = await mountProblems(paidOnly)
    useI18nStore().set('zh')

    await wrapper.find('[data-testid="random-btn"]').trigger('click')

    // nothing free to pick: no navigation, and the reason lands in a toast
    expect(pushSpy).not.toHaveBeenCalled()
    const toast = useToastStore()
    expect(toast.items.some((item) => item.text.includes('付费题'))).toBe(true)
  })

  it('random button is disabled when no problem matches the filters', async () => {
    const wrapper = await mountProblems()
    await wrapper.find('[data-testid="status-select"]').setValue('favorite')
    expect(wrapper.find('[data-testid="random-btn"]').attributes('disabled')).toBeDefined()
  })

  it('density toggle persists across remounts', async () => {
    let wrapper = await mountProblems()
    expect(wrapper.find('.problem-list').classes()).not.toContain('dense')
    await wrapper.find('[data-testid="density-btn"]').trigger('click')
    expect(wrapper.find('.problem-list').classes()).toContain('dense')
    expect(localStorage.getItem('algocoach-density')).toBe('dense')
    wrapper.unmount()

    // a fresh mount adopts the persisted density
    setActivePinia(createPinia())
    wrapper = await mountProblems()
    expect(wrapper.find('.problem-list').classes()).toContain('dense')
  })

  it('shows skeleton rows while loading instead of an empty page', async () => {
    let resolveList
    apiMocks.getProblems.mockReturnValue(
      new Promise((resolve) => {
        resolveList = resolve
      })
    )
    const wrapper = mount(Problems, {
      global: {
        plugins: [createPinia()],
        stubs: { RouterLink: { template: '<a><slot/></a>' } },
      },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="skeleton-list"]').exists()).toBe(true)
    resolveList({ problems: [], synced_at: null })
    await flushPromises()
    expect(wrapper.find('[data-testid="empty-problems"]').exists()).toBe(true)
  })
})
