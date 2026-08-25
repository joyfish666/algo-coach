import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useI18nStore } from './i18n'

function setNavigatorLanguage(lang) {
  Object.defineProperty(window.navigator, 'language', {
    value: lang,
    configurable: true,
  })
}

describe('i18n store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('detects zh from navigator language when nothing stored', () => {
    setNavigatorLanguage('zh-CN')
    const i18n = useI18nStore()
    expect(i18n.lang).toBe('zh')
  })

  it('detects en for non-chinese locales', () => {
    setNavigatorLanguage('en-US')
    const i18n = useI18nStore()
    expect(i18n.lang).toBe('en')
  })

  it('set persists to localStorage and switches messages', () => {
    const i18n = useI18nStore()
    i18n.set('zh')
    expect(localStorage.getItem('algocoach-lang')).toBe('zh')
    expect(i18n.t('nav_problems')).toBe('题库')
    i18n.set('en')
    expect(i18n.t('nav_problems')).toBe('Problems')
  })

  it('rejects unsupported languages', () => {
    const i18n = useI18nStore()
    i18n.set('xx')
    expect(i18n.lang).not.toBe('xx')
  })

  it('falls back to key for unknown entries and interpolates params', () => {
    const i18n = useI18nStore()
    i18n.set('en')
    expect(i18n.t('no_such_key')).toBe('no_such_key')
    expect(i18n.messages.nav_problems).toBeDefined()
    expect(i18n.t('{a}+{b}', { a: 1, b: 2 })).toBe('1+2')
  })

  it('formatDateTime follows the UI language, not the browser locale', () => {
    const i18n = useI18nStore()
    setNavigatorLanguage('en-US')
    i18n.set('zh')
    // zh-CN renders the ISO timestamp with Chinese date/time characters
    const zh = i18n.formatDateTime('2026-08-24T10:00:00')
    expect(zh).toMatch(/2026/)
    expect(zh).not.toMatch(/PM|AM/)

    i18n.set('en')
    const en = i18n.formatDateTime('2026-08-24T22:00:00')
    expect(en).toMatch(/PM|pm/)
  })

  it('formatDateTime passes through values it cannot parse', () => {
    const i18n = useI18nStore()
    expect(i18n.formatDateTime('not-a-date')).toBe('not-a-date')
  })
})
