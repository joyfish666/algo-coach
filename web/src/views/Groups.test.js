import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const apiMocks = {
  getGroups: vi.fn(),
  getProblems: vi.fn(),
  createGroup: vi.fn(),
  renameGroup: vi.fn(),
  moveGroup: vi.fn(),
  deleteGroup: vi.fn(),
  addGroupItems: vi.fn(),
  removeGroupItem: vi.fn(),
  setGroupOrder: vi.fn(),
  setGroupMarked: vi.fn(),
  importGroups: vi.fn(),
  exportGroups: vi.fn(),
}

vi.mock('../api', () => ({
  api: new Proxy({}, {
    get: (_t, prop) => apiMocks[prop] ?? vi.fn(),
  }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/groups', query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import Groups from './Groups.vue'
import { useGroupsStore } from '../stores/groups'

const TREE = [
  { id: 'r1', name: '2026', parent: null, slugs: ['two-sum'] },
  { id: 'c1', name: '0830', parent: 'r1', slugs: [] },
]
const PROBLEMS = [
  { slug: 'two-sum', frontend_id: '1', title_cn: '两数之和', difficulty: 'easy', tags: [] },
]

async function mountGroups(tree = TREE, problems = PROBLEMS) {
  apiMocks.getGroups.mockResolvedValue({
    groups: JSON.parse(JSON.stringify(tree)),
  })
  apiMocks.getProblems.mockResolvedValue({
    total: problems.length,
    problems: JSON.parse(JSON.stringify(problems)),
  })
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(Groups, {
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

describe('Groups view', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    Object.values(apiMocks).forEach((fn) => fn.mockReset())
  })

  it('renders the tree recursively and resolves problem titles', async () => {
    const wrapper = await mountGroups()
    expect(wrapper.findAll('[data-testid="group-node"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('2026')
    expect(wrapper.text()).toContain('0830')
    expect(wrapper.text()).toContain('两数之和')
  })

  it('marks slugs missing from the cache as unresolved instead of hiding them', async () => {
    const wrapper = await mountGroups(
      [{ id: 'r9', name: '外地导入', parent: null, slugs: ['not-synced-yet'] }]
    )
    expect(wrapper.find('[data-testid="group-unknown-item"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('not-synced-yet')
  })

  it('shows the empty state and opens the create card from it', async () => {
    const wrapper = await mountGroups([], [])
    expect(wrapper.find('[data-testid="groups-empty"]').exists()).toBe(true)
    await wrapper.find('[data-testid="groups-empty"] .btn-primary').trigger('click')
    expect(wrapper.find('[data-testid="groups-create-name"]').exists()).toBe(true)
  })

  it('creates a root group from the header form', async () => {
    const wrapper = await mountGroups()
    apiMocks.createGroup.mockResolvedValue({ id: 'n1', name: '新组', parent: null, slugs: [] })
    await wrapper.find('[data-testid="groups-create-btn"]').trigger('click')
    await wrapper.find('[data-testid="groups-create-name"]').setValue('新组')
    await wrapper.find('[data-testid="groups-create-submit"]').trigger('click')
    await flushPromises()
    expect(apiMocks.createGroup).toHaveBeenCalledWith('新组', null)
  })

  it('deletes a group only after the two-step confirmation', async () => {
    const wrapper = await mountGroups()
    apiMocks.deleteGroup.mockResolvedValue({ deleted: true, removed_groups: 1, removed_slugs: 1 })
    const del = wrapper.findAll('[data-testid="group-node"]')[0].find('[data-testid="group-delete"]')
    await del.trigger('click')
    expect(apiMocks.deleteGroup).not.toHaveBeenCalled()
    await del.trigger('click')
    await flushPromises()
    expect(apiMocks.deleteGroup).toHaveBeenCalledWith('r1')
  })

  it('adds a problem through the node search suggestions', async () => {
    const wrapper = await mountGroups()
    await wrapper.findAll('[data-testid="group-node"]')[1]
      .find('[data-testid="group-add-problem"]')
      .trigger('click')
    const search = wrapper.findAll('[data-testid="group-node"]')[1].find('[data-testid="group-problem-search"]')
    await search.setValue('两数')
    const suggestion = wrapper.find('[data-testid="suggest-two-sum"]')
    expect(suggestion.exists()).toBe(true)
    await suggestion.trigger('click')
    await flushPromises()
    // the suggestion resolves to the slug and lands in the child node c1
    expect(apiMocks.addGroupItems).toHaveBeenCalledWith('c1', ['two-sum'])
  })

  it('exports all groups; a clipboard failure surfaces the code in a box', async () => {
    const wrapper = await mountGroups()
    apiMocks.exportGroups.mockResolvedValue({ code: 'algocoach-groups:v1:abc' })
    await wrapper.find('[data-testid="groups-export-btn"]').trigger('click')
    await flushPromises()
    expect(apiMocks.exportGroups).toHaveBeenCalledWith(null)
    // jsdom has no async clipboard: the fallback box must show the code
    expect(wrapper.find('[data-testid="groups-export-box"]').exists()).toBe(true)
  })

  it('collapses a group, persists the state and hides its body', async () => {
    const wrapper = await mountGroups()
    const root = wrapper.findAll('[data-testid="group-node"]')[0]
    // jsdom's getComputedStyle does not reflect v-show's inline display, so
    // assert the inline style instead of isVisible()
    const isHidden = (node) => (node.attributes('style') || '').includes('display: none')
    expect(isHidden(root.find('.gnode-body'))).toBe(false)

    await root.find('[data-testid="group-collapse"]').trigger('click')
    expect(isHidden(root.find('.gnode-body'))).toBe(true)
    expect(localStorage.getItem('algocoach-group-collapsed')).toContain('r1')

    // clicking the group name toggles it back open
    await root.find('[data-testid="group-name"]').trigger('click')
    expect(isHidden(root.find('.gnode-body'))).toBe(false)
  })

  it('marks and unmarks a problem as key through the store', async () => {
    const wrapper = await mountGroups()
    apiMocks.setGroupMarked.mockResolvedValue({ marked: ['two-sum'] })
    const root = wrapper.findAll('[data-testid="group-node"]')[0]

    const mark = root.find('[data-testid="item-mark"]')
    await mark.trigger('click')
    await flushPromises()
    expect(apiMocks.setGroupMarked).toHaveBeenCalledWith('r1', ['two-sum'])

    // a tree that already carries the mark renders the active state and the
    // next click clears it
    apiMocks.getGroups.mockResolvedValue({
      groups: [
        { id: 'r1', name: '2026', parent: null, slugs: ['two-sum'], marked: ['two-sum'] },
      ],
    })
    await useGroupsStore().refresh()
    await flushPromises()
    const marked = wrapper.findAll('[data-testid="group-node"]')[0]
    expect(marked.find('[data-testid="item-mark"]').classes()).toContain('mark-active')
    await marked.find('[data-testid="item-mark"]').trigger('click')
    await flushPromises()
    expect(apiMocks.setGroupMarked).toHaveBeenLastCalledWith('r1', [])
  })

  it('imports a pasted share code', async () => {
    const wrapper = await mountGroups()
    apiMocks.importGroups.mockResolvedValue({ created: 2, slugs: 1, root_ids: ['x'] })
    await wrapper.find('[data-testid="groups-import-btn"]').trigger('click')
    await wrapper.find('[data-testid="groups-import-area"]').setValue('algocoach-groups:v1:abc')
    await wrapper.find('[data-testid="groups-import-submit"]').trigger('click')
    await flushPromises()
    expect(apiMocks.importGroups).toHaveBeenCalledWith('algocoach-groups:v1:abc')
  })
})
