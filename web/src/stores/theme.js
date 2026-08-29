import { defineStore } from 'pinia'

import { STORAGE_KEYS, readStorage, writeStorage } from '../utils/storage'

// module-level so re-mounting App (HMR/tests) cannot stack duplicate
// matchMedia listeners that would never be removed
let mediaBound = false

function readStoredTheme() {
  return readStorage(STORAGE_KEYS.theme)
}

export const useThemeStore = defineStore('theme', {
  state: () => ({
    theme: readStoredTheme() || 'system',
  }),
  getters: {
    resolved(state) {
      if (state.theme !== 'system') return state.theme
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    },
  },
  actions: {
    apply() {
      document.documentElement.setAttribute('data-theme', this.resolved)
    },
    set(theme) {
      this.theme = theme
      writeStorage(STORAGE_KEYS.theme, theme)
      this.apply()
    },
    init() {
      this.apply()
      if (mediaBound) return
      mediaBound = true
      window
        .matchMedia('(prefers-color-scheme: dark)')
        .addEventListener('change', () => {
          if (this.theme === 'system') this.apply()
        })
    },
  },
})
