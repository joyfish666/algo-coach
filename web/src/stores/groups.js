import { defineStore } from 'pinia'

import { api } from '../api'
import { STORAGE_KEYS, readJsonStorage, writeJsonStorage } from '../utils/storage'

// One shared snapshot of the group tree (~/.algocoach/groups.json behind
// /api/groups). Every mutation re-fetches: the document is tiny, and a
// refetch keeps the flat parent-pointer list, sibling order, slug membership
// and key-problem marks exactly consistent with the server instead of
// mirroring tree surgery client-side. The list page rows, the workbench meta
// row and the /groups page all read this one snapshot.
export const useGroupsStore = defineStore('groups', {
  state: () => ({
    groups: [],
    loaded: false,
    loading: false,
    // {groupId: true} for collapsed tree nodes; a UI preference persisted in
    // localStorage so the plan keeps its shape across visits
    collapsedIds: readJsonStorage(STORAGE_KEYS.groupCollapsed) || {},
  }),
  getters: {
    rootGroups(state) {
      return state.groups.filter((group) => !group.parent)
    },
    childrenOf(state) {
      return (parentId) => state.groups.filter((group) => group.parent === parentId)
    },
    byId(state) {
      return new Map(state.groups.map((group) => [group.id, group]))
    },
    // "2026 / 0830" labels for the flat picker list
    pathOf(state) {
      const byId = new Map(state.groups.map((group) => [group.id, group]))
      return (id) => {
        const names = []
        let cursor = byId.get(id)
        let guard = 0
        while (cursor && guard++ < 32) {
          names.unshift(cursor.name)
          cursor = byId.get(cursor.parent)
        }
        return names.join(' / ')
      }
    },
    groupsOfSlug(state) {
      return (slug) => state.groups.filter((group) => group.slugs.includes(slug))
    },
    subtreeIds(state) {
      const children = new Map()
      for (const group of state.groups) {
        const key = group.parent || ''
        if (!children.has(key)) children.set(key, [])
        children.get(key).push(group.id)
      }
      return (id) => {
        const out = new Set()
        const stack = [id]
        while (stack.length) {
          const current = stack.pop()
          if (out.has(current)) continue
          out.add(current)
          for (const childId of children.get(current) || []) stack.push(childId)
        }
        return out
      }
    },
  },
  actions: {
    async ensure() {
      if (!this.loaded && !this.loading) await this.refresh()
    },
    async refresh() {
      this.loading = true
      try {
        const data = await api.getGroups()
        this.groups = data?.groups || []
        this.loaded = true
      } finally {
        this.loading = false
      }
    },
    async create(name, parent = null) {
      const group = await api.createGroup(name, parent)
      await this.refresh()
      return group || null
    },
    async rename(id, name) {
      await api.renameGroup(id, name)
      await this.refresh()
    },
    async move(id, parent, index = null) {
      await api.moveGroup(id, parent, index)
      await this.refresh()
    },
    async remove(id) {
      await api.deleteGroup(id)
      await this.refresh()
    },
    async addSlugs(id, slugs) {
      await api.addGroupItems(id, slugs)
      await this.refresh()
    },
    async removeSlug(id, slug) {
      await api.removeGroupItem(id, slug)
      await this.refresh()
    },
    async setMarked(id, slugs) {
      await api.setGroupMarked(id, slugs)
      await this.refresh()
    },
    async toggleMarked(id, slug) {
      const group = this.byId.get(id)
      const marked = group?.marked || []
      const next = marked.includes(slug)
        ? marked.filter((s) => s !== slug)
        : [...marked, slug]
      await this.setMarked(id, next)
    },
    isCollapsed(id) {
      return !!this.collapsedIds[id]
    },
    toggleCollapsed(id) {
      if (this.collapsedIds[id]) {
        delete this.collapsedIds[id]
      } else {
        this.collapsedIds[id] = true
      }
      // replace the object so reactivity + writeJsonStorage see the change
      this.collapsedIds = { ...this.collapsedIds }
      writeJsonStorage(STORAGE_KEYS.groupCollapsed, this.collapsedIds)
    },
    // deep links (workbench chips) must reveal the target even when an
    // ancestor is collapsed
    expandTo(id) {
      const byId = this.byId
      let cursor = byId.get(id)
      let guard = 0
      let changed = false
      while (cursor && guard++ < 32) {
        if (this.collapsedIds[cursor.id]) {
          delete this.collapsedIds[cursor.id]
          changed = true
        }
        cursor = byId.get(cursor.parent)
      }
      if (changed) {
        this.collapsedIds = { ...this.collapsedIds }
        writeJsonStorage(STORAGE_KEYS.groupCollapsed, this.collapsedIds)
      }
    },
    async reorder(id, slugs) {
      await api.setGroupOrder(id, slugs)
      await this.refresh()
    },
    async importCode(code) {
      const result = await api.importGroups(code)
      await this.refresh()
      return result
    },
    async exportCode(ids = null) {
      const result = await api.exportGroups(ids)
      return result?.code || ''
    },
  },
})
