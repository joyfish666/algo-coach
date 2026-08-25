import { defineStore } from 'pinia'

const STORAGE_KEY = 'algocoach-theme'
// module-level so re-mounting App (HMR/tests) cannot stack duplicate
// matchMedia listeners that would never be removed
let mediaBound = false

function readStoredTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
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
      try {
        localStorage.setItem(STORAGE_KEY, theme)
      } catch {
      }
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
