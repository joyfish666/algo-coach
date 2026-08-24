import { defineStore } from 'pinia'

import { useI18nStore } from './i18n'

let seed = 0

function resolveText({ key, params, text }) {
  if (key) {
    const i18n = useI18nStore()
    return i18n.t(key, params)
  }
  return text || ''
}

export const useToastStore = defineStore('toast', {
  state: () => ({
    items: [],
  }),
  actions: {
    /**
     * Push one notification. Errors stay until dismissed (a transient
     * failure the user never sees is a bug); successes auto-expire so a
     * quiet operation does not leave residue on screen.
     */
    push({ kind = 'info', key, params, text, duration } = {}) {
      seed += 1
      const id = seed
      const item = {
        id,
        kind,
        text: resolveText({ key, params, text }),
      }
      this.items.push(item)
      if (item.text.length > 300) item.text = `${item.text.slice(0, 300)}…`
      if (kind !== 'error') {
        setTimeout(() => this.dismiss(id), duration ?? 4000)
      }
      return id
    },
    success(payload) {
      return this.push({ ...payload, kind: 'success' })
    },
    error(payload) {
      return this.push({ ...payload, kind: 'error' })
    },
    dismiss(id) {
      this.items = this.items.filter((item) => item.id !== id)
    },
  },
})
