import { defineStore } from 'pinia'

import { api } from '../api'
import { useI18nStore } from './i18n'
import { useToastStore } from './toast'

const POLL_INTERVAL_MS = 1000
const POLL_MAX_FAILURES = 5

let pollTimer = null
let pollInFlight = false

/**
 * Global sync orchestration.
 *
 * Root cause this replaces: polling used to be owned by the Problems view,
 * so navigating away silently dropped the UI half of an in-flight backend
 * sync, and returning showed a stale "idle" button while the engine was
 * still working. The store survives route changes; any view just renders
 * its state, and App.vue re-adopts a running backend sync at startup.
 */
export const useSyncStore = defineStore('sync', {
  state: () => ({
    // idle | running | done | failed | lost
    phase: 'idle',
    fetched: 0,
    total: null,
    pollFailures: 0,
  }),
  getters: {
    running: (state) => state.phase === 'running',
    label(state) {
      const i18n = useI18nStore()
      if (state.phase !== 'running') return i18n.t('sync_now')
      const total = state.total
      if (!total) return i18n.t('sync_running', { fetched: state.fetched, total: '?' })
      return i18n.t('sync_running', { fetched: state.fetched, total })
    },
  },
  actions: {
    async start() {
      if (this.running) return
      const toast = useToastStore()
      try {
        try {
          await api.startSync()
        } catch (err) {
          // someone else (another tab/page) already started the engine;
          // adopt it instead of failing the click
          if (err.status !== 409) throw err
        }
        this.phase = 'running'
        this.fetched = 0
        this.total = null
        this.pollFailures = 0
        this.beginPolling()
      } catch (err) {
        this.phase = 'failed'
        toast.error({ text: err.message || String(err) })
      }
    },

    /** Re-attach to a backend sync that is already running (page reload or
     * first navigation mid-sync). Never announces anything on its own. */
    adoptFromStatus(syncSnapshot) {
      if (!syncSnapshot || !syncSnapshot.running || this.running) return
      this.phase = 'running'
      this.fetched = syncSnapshot.fetched || 0
      this.total = syncSnapshot.total ?? null
      this.pollFailures = 0
      this.beginPolling()
    },

    beginPolling() {
      this.stopPolling()
      pollTimer = setInterval(() => this.poll(), POLL_INTERVAL_MS)
      this.poll()
    },

    stopPolling() {
      if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
    },

    async poll() {
      if (pollInFlight) return // a >1s response must not stack overlapping polls
      const i18n = useI18nStore()
      const toast = useToastStore()
      let progress
      pollInFlight = true
      try {
        progress = await api.getSyncProgress()
        this.pollFailures = 0
      } catch {
        // bounded retry budget: without it a persistently failing endpoint
        // keeps the UI in "running" forever (e.g. backend restarted mid-sync)
        this.pollFailures += 1
        if (this.pollFailures >= POLL_MAX_FAILURES) {
          this.stopPolling()
          this.phase = 'lost'
          toast.error({ key: 'sync_lost' })
        }
        return
      } finally {
        pollInFlight = false
      }

      this.fetched = progress.fetched || 0
      this.total = progress.total ?? null

      if (progress.running) return
      this.stopPolling()

      if (progress.error) {
        this.phase = 'failed'
        toast.error({
          text: `${i18n.t('sync_error')}: ${progress.error}`,
        })
        return
      }

      // A finished engine reports started_at/finished_at; an engine that
      // never ran since boot reports neither plus zero rows. Collapsing that
      // second shape into "done" used to fake success after a backend
      // restart swallowed the run mid-flight.
      const genuinelyFinished = Boolean(progress.started_at || progress.finished_at)
      if (genuinelyFinished) {
        this.phase = 'done'
        toast.success({ key: 'sync_done' })
      } else {
        this.phase = 'lost'
        toast.error({ key: 'sync_interrupted' })
      }
    },

    reset() {
      this.stopPolling()
      this.phase = 'idle'
      this.fetched = 0
      this.total = null
      this.pollFailures = 0
    },
  },
})
