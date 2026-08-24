import { defineStore } from 'pinia'

import { api } from '../api'

export const useStatusStore = defineStore('status', {
  state: () => ({
    loaded: false,
    reachable: true,
    configured: false,
    version: '',
    dataDir: '',
    sync: {},
  }),
  actions: {
    async refresh() {
      try {
        const data = await api.getStatus()
        this.configured = Boolean(data.configured)
        this.version = data.version || ''
        this.dataDir = data.data_dir || ''
        this.sync = data.sync || {}
        this.reachable = true
      } catch {
        this.reachable = false
      } finally {
        this.loaded = true
      }
    },
  },
})
