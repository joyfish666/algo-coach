import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = {
  getGroups: vi.fn(),
  createGroup: vi.fn(),
  renameGroup: vi.fn(),
  moveGroup: vi.fn(),
  deleteGroup: vi.fn(),
  addGroupItems: vi.fn(),
  removeGroupItem: vi.fn(),
  setGroupOrder: vi.fn(),
  importGroups: vi.fn(),
  exportGroups: vi.fn(),
}

vi.mock('../api', () => ({
  api: new Proxy({}, {
    get: (_t, prop) => apiMocks[prop] ?? vi.fn(),
  }),
}))

import { useGroupsStore } from './groups'

const TREE = [
  { id: 'r1', name: '2026', parent: null, slugs: [] },
  { id: 'c1', name: '0830', parent: 'r1', slugs: ['two-sum'] },
  { id: 'c2', name: '0831', parent: 'r1', slugs: [] },
]

function mockTree(tree = TREE) {
  apiMocks.getGroups.mockResolvedValue({ groups: JSON.parse(JSON.stringify(tree)) })
}

describe('groups store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    Object.values(apiMocks).forEach((fn) => fn.mockReset())
  })

  it('ensure() loads once even when called concurrently', async () => {
    mockTree()
    const store = useGroupsStore()
    await Promise.all([store.ensure(), store.ensure()])
    expect(apiMocks.getGroups).toHaveBeenCalledTimes(1)
    expect(store.loaded).toBe(true)
  })

  it('derives roots, sibling order, paths, membership and subtrees', async () => {
    mockTree()
    const store = useGroupsStore()
    await store.ensure()
    expect(store.rootGroups.map((g) => g.id)).toEqual(['r1'])
    expect(store.childrenOf('r1').map((g) => g.id)).toEqual(['c1', 'c2'])
    expect(store.pathOf('c1')).toBe('2026 / 0830')
    expect(store.pathOf('r1')).toBe('2026')
    expect(store.groupsOfSlug('two-sum').map((g) => g.id)).toEqual(['c1'])
    expect(store.groupsOfSlug('missing').length).toBe(0)
    expect(store.subtreeIds('r1')).toEqual(new Set(['r1', 'c1', 'c2']))
    expect(store.subtreeIds('c2')).toEqual(new Set(['c2']))
  })

  it('create returns the created group and refreshes the snapshot', async () => {
    mockTree()
    const store = useGroupsStore()
    await store.ensure()
    apiMocks.createGroup.mockResolvedValue({ id: 'n1', name: '新组', parent: null, slugs: [] })
    const created = await store.create('新组')
    expect(apiMocks.createGroup).toHaveBeenCalledWith('新组', null)
    expect(created.id).toBe('n1')
    expect(apiMocks.getGroups).toHaveBeenCalledTimes(2)
  })

  it('item mutations re-fetch so membership stays server-consistent', async () => {
    mockTree()
    const store = useGroupsStore()
    await store.ensure()
    apiMocks.addGroupItems.mockResolvedValue({})
    await store.addSlugs('c2', ['add-two-numbers'])
    expect(apiMocks.addGroupItems).toHaveBeenCalledWith('c2', ['add-two-numbers'])
    expect(apiMocks.getGroups).toHaveBeenCalledTimes(2)
    apiMocks.removeGroupItem.mockResolvedValue({})
    await store.removeSlug('c1', 'two-sum')
    expect(apiMocks.removeGroupItem).toHaveBeenCalledWith('c1', 'two-sum')
  })

  it('tree mutations re-fetch (rename / move / delete / reorder)', async () => {
    mockTree()
    const store = useGroupsStore()
    await store.ensure()
    apiMocks.renameGroup.mockResolvedValue({})
    apiMocks.moveGroup.mockResolvedValue({})
    apiMocks.deleteGroup.mockResolvedValue({})
    apiMocks.setGroupOrder.mockResolvedValue({})
    await store.rename('c1', '改名')
    expect(apiMocks.renameGroup).toHaveBeenCalledWith('c1', '改名')
    await store.move('c1', null, 2)
    expect(apiMocks.moveGroup).toHaveBeenCalledWith('c1', null, 2)
    await store.remove('c1')
    expect(apiMocks.deleteGroup).toHaveBeenCalledWith('c1')
    await store.reorder('c1', [])
    expect(apiMocks.setGroupOrder).toHaveBeenCalledWith('c1', [])
    expect(apiMocks.getGroups).toHaveBeenCalledTimes(5)
  })

  it('import/export pass through and refresh', async () => {
    mockTree()
    const store = useGroupsStore()
    await store.ensure()
    apiMocks.importGroups.mockResolvedValue({ created: 2, slugs: 1, root_ids: ['x'] })
    const result = await store.importCode('algocoach-groups:v1:abc')
    expect(result.created).toBe(2)
    expect(apiMocks.getGroups).toHaveBeenCalledTimes(2)
    apiMocks.exportGroups.mockResolvedValue({ code: 'algocoach-groups:v1:xyz' })
    expect(await store.exportCode(null)).toBe('algocoach-groups:v1:xyz')
    expect(await store.exportCode(['r1'])).toBe('algocoach-groups:v1:xyz')
    expect(apiMocks.exportGroups).toHaveBeenLastCalledWith(['r1'])
  })

  it('tolerates an undefined payload shape', async () => {
    apiMocks.getGroups.mockResolvedValue(undefined)
    const store = useGroupsStore()
    await store.refresh()
    expect(store.groups).toEqual([])
    expect(store.loaded).toBe(true)
  })
})
