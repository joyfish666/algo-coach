import { defineStore } from 'pinia'

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
        const response = await fetch('/api/status')
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const data = await response.json()
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
