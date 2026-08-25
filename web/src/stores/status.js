import { defineStore } from 'pinia'

import { api } from '../api'

// App.vue and the router guard both refresh on startup; coalescing the
// concurrent calls into one request keeps /api/status single-flight.
let inflight = null

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
    refresh() {
      if (inflight) return inflight
      inflight = (async () => {
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
          inflight = null
        }
      })()
      return inflight
    },
  },
})
