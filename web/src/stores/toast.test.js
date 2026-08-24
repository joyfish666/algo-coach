import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useI18nStore } from './i18n'
import { useToastStore } from './toast'

describe('toast store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('success toasts auto-expire', () => {
    const toast = useToastStore()
    const i18n = useI18nStore()
    toast.success({ key: 'sync_done' })
    expect(toast.items).toHaveLength(1)
    expect(toast.items[0].text).toBe(i18n.t('sync_done'))
    vi.advanceTimersByTime(4100)
    expect(toast.items).toHaveLength(0)
  })

  it('error toasts persist until dismissed - an unseen failure is a bug', () => {
    const toast = useToastStore()
    toast.error({ text: 'boom' })
    vi.advanceTimersByTime(60000)
    expect(toast.items).toHaveLength(1)
    toast.dismiss(toast.items[0].id)
    expect(toast.items).toHaveLength(0)
  })

  it('translates keys and interpolates params at push time', () => {
    const toast = useToastStore()
    toast.error({ key: 'sync_error' })
    expect(toast.items[0].text).toBe(useI18nStore().t('sync_error'))
  })

  it('truncates absurdly long server messages', () => {
    const toast = useToastStore()
    toast.push({ text: 'x'.repeat(1000) })
    expect(toast.items[0].text.length).toBeLessThanOrEqual(301)
    expect(toast.items[0].text.endsWith('…')).toBe(true)
  })
})
