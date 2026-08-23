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
})
