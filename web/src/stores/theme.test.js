import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useThemeStore } from './theme'

function stubMatchMedia(matchesDark) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockReturnValue({
      matches: matchesDark,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })
  )
}

describe('theme store', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    setActivePinia(createPinia())
  })

  it('defaults to system and resolves light when system is light', () => {
    stubMatchMedia(false)
    const theme = useThemeStore()
    expect(theme.theme).toBe('system')
    theme.init()
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('resolves dark when system prefers dark', () => {
    stubMatchMedia(true)
    const theme = useThemeStore()
    theme.init()
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('persists manual choice to localStorage and applies attribute', () => {
    stubMatchMedia(false)
    const theme = useThemeStore()
    theme.set('dark')
    expect(localStorage.getItem('algocoach-theme')).toBe('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')

    theme.set('light')
    expect(localStorage.getItem('algocoach-theme')).toBe('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('stored choice overrides system preference on init', () => {
    localStorage.setItem('algocoach-theme', 'dark')
    stubMatchMedia(false)
    const theme = useThemeStore()
    expect(theme.theme).toBe('dark')
    theme.init()
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })
})
