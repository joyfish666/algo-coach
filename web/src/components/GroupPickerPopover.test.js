import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const apiMocks = {
  getGroups: vi.fn(),
  addGroupItems: vi.fn().mockResolvedValue({}),
  removeGroupItem: vi.fn().mockResolvedValue({}),
  createGroup: vi.fn(),
}

vi.mock('../api', () => ({
  api: new Proxy({}, {
    get: (_t, prop) => apiMocks[prop] ?? vi.fn(),
  }),
}))

import GroupPickerPopover from './GroupPickerPopover.vue'
import ProblemCard from './ProblemCard.vue'

const TREE = [
  { id: 'r1', name: '2026', parent: null, slugs: [] },
  { id: 'c1', name: '0830', parent: 'r1', slugs: ['two-sum'] },
]

async function mountPopover(slug = 'two-sum') {
  apiMocks.getGroups.mockResolvedValue({ groups: JSON.parse(JSON.stringify(TREE)) })
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(GroupPickerPopover, {
    props: { slug, align: 'right' },
    global: {
      plugins: [pinia],
      stubs: { RouterLink: { template: '<a><slot/></a>' } },
    },
  })
  await flushPromises()
  return wrapper
}

describe('GroupPickerPopover', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    Object.values(apiMocks).forEach((fn) => fn.mockClear())
  })

  it('loads the tree lazily on first open and lists flat paths', async () => {
    const wrapper = await mountPopover()
    expect(wrapper.find('.grp-pop').exists()).toBe(false)
    await wrapper.find('[data-testid="group-toggle"]').trigger('click')
    await flushPromises()
    expect(apiMocks.getGroups).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.grp-pop').exists()).toBe(true)
    const rows = wrapper.findAll('.grp-row')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('2026')
    expect(rows[0].classes()).not.toContain('member')
    expect(rows[1].text()).toContain('2026 / 0830')
    // the default slug two-sum lives in c1: flat path + member check mark
    expect(rows[1].classes()).toContain('member')
  })

  it('marks membership with a check and toggles it off on click', async () => {
    const wrapper = await mountPopover('two-sum')
    await wrapper.find('[data-testid="group-toggle"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="group-option-c1"]').classes()).toContain('member')
    await wrapper.find('[data-testid="group-option-c1"]').trigger('click')
    await flushPromises()
    expect(apiMocks.removeGroupItem).toHaveBeenCalledWith('c1', 'two-sum')
    expect(apiMocks.addGroupItems).not.toHaveBeenCalled()
  })

  it('adds a non-member group on click', async () => {
    const wrapper = await mountPopover('two-sum')
    await wrapper.find('[data-testid="group-toggle"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="group-option-r1"]').trigger('click')
    await flushPromises()
    expect(apiMocks.addGroupItems).toHaveBeenCalledWith('r1', ['two-sum'])
  })

  it('search filters the flat list by path', async () => {
    const wrapper = await mountPopover()
    await wrapper.find('[data-testid="group-toggle"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="group-search"]').setValue('0830')
    const rows = wrapper.findAll('.grp-row')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('0830')
  })

  it('creates a new root group and adds the problem to it', async () => {
    const wrapper = await mountPopover('two-sum')
    await wrapper.find('[data-testid="group-toggle"]').trigger('click')
    await flushPromises()
    apiMocks.createGroup.mockResolvedValue({ id: 'n1', name: '冲刺组', parent: null, slugs: [] })
    await wrapper.find('[data-testid="group-new-name"]').setValue('冲刺组')
    await wrapper.find('[data-testid="group-create-add"]').trigger('click')
    await flushPromises()
    expect(apiMocks.createGroup).toHaveBeenCalledWith('冲刺组', null)
    expect(apiMocks.addGroupItems).toHaveBeenCalledWith('n1', ['two-sum'])
  })

  it('closes when the backdrop is clicked', async () => {
    const wrapper = await mountPopover()
    await wrapper.find('[data-testid="group-toggle"]').trigger('click')
    await flushPromises()
    await wrapper.find('.grp-backdrop').trigger('click')
    expect(wrapper.find('.grp-pop').exists()).toBe(false)
  })
})

describe('ProblemCard group entry', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    Object.values(apiMocks).forEach((fn) => fn.mockClear())
  })

  it('opens the picker from the row without navigating', async () => {
    apiMocks.getGroups.mockResolvedValue({ groups: JSON.parse(JSON.stringify(TREE)) })
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(ProblemCard, {
      props: {
        row: {
          slug: 'two-sum',
          frontend_id: '1',
          title_cn: '两数之和',
          difficulty: 'easy',
          tags: [],
          favorite: false,
        },
      },
      global: {
        plugins: [pinia],
        stubs: { RouterLink: { template: '<a><slot/></a>' } },
      },
    })
    await wrapper.find('[data-testid="group-toggle"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.grp-pop').exists()).toBe(true)
    expect(apiMocks.getGroups).toHaveBeenCalledTimes(1)
  })
})
