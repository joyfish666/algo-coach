import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const validateCookieMock = vi.fn()

vi.mock('../api', () => ({
  api: {
    validateCookie: (...args) => validateCookieMock(...args),
    getSettings: vi.fn().mockResolvedValue({ default_language: 'cpp', configured: false }),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import Setup from './Setup.vue'

function mountWizard() {
  return mount(Setup, { global: { plugins: [createPinia()] } })
}

describe('setup wizard step 1 (cookie)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    validateCookieMock.mockReset()
    validateCookieMock.mockResolvedValue({ ok: true })
  })

  async function fillSimpleMode(wrapper) {
    await wrapper.find('[data-testid="session-input"]').setValue('sess-value')
    await wrapper.find('[data-testid="csrf-input"]').setValue('tok-123')
  }

  it('keeps next disabled until validation succeeds, then enables it', async () => {
    const wrapper = mountWizard()
    const next = wrapper.find('[data-testid="cookie-next"]')
    expect(next.attributes('disabled')).toBeDefined()

    await fillSimpleMode(wrapper)
    const validateBtn = wrapper.find('[data-testid="cookie-validate"]')
    expect(validateBtn.attributes('disabled')).toBeUndefined()

    await validateBtn.trigger('click')
    await flushPromises()

    expect(validateCookieMock).toHaveBeenCalledWith(
      'LEETCODE_SESSION=sess-value; csrftoken=tok-123'
    )
    expect(wrapper.find('[data-testid="cookie-valid"]').exists()).toBe(true)
    expect(next.attributes('disabled')).toBeUndefined()
  })

  it('shows server error and keeps next disabled when validation fails', async () => {
    // the rejection mirrors what api.js handle() throws: the localized
    // message lands on err.message, the payload rides along for context
    validateCookieMock.mockRejectedValue({
      message: 'Cookie 已失效，请重新粘贴',
      status: 401,
      payload: { error: { kind: 'AuthError', message_key: 'cookie_invalid', message: 'Cookie 已失效，请重新粘贴' } },
    })
    const wrapper = mountWizard()
    await fillSimpleMode(wrapper)
    await wrapper.find('[data-testid="cookie-validate"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="cookie-error"]').text()).toContain('Cookie 已失效')
    expect(wrapper.find('[data-testid="cookie-next"]').attributes('disabled')).toBeDefined()
  })

  it('composes whole-string mode from the advanced tab', async () => {
    const wrapper = mountWizard()
    await wrapper.findAll('.mode-tabs button')[1].trigger('click')
    await wrapper.find('[data-testid="cookie-input"]').setValue('a=1; csrftoken=t; LEETCODE_SESSION=s')
    await wrapper.find('[data-testid="cookie-validate"]').trigger('click')
    await flushPromises()
    expect(validateCookieMock).toHaveBeenCalledWith('a=1; csrftoken=t; LEETCODE_SESSION=s')
  })

  it('allows immediate retry after failed validation while next stays locked', async () => {
    const wrapper = mountWizard()
    const validateBtn = wrapper.find('[data-testid="cookie-validate"]')
    expect(validateBtn.attributes('disabled')).toBeDefined()

    await fillSimpleMode(wrapper)
    expect(validateBtn.attributes('disabled')).toBeUndefined()

    validateCookieMock.mockRejectedValue({ message: 'fail' })
    await validateBtn.trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="cookie-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cookie-next"]').attributes('disabled')).toBeDefined()
    expect(validateBtn.attributes('disabled')).toBeUndefined()

    await wrapper.find('[data-testid="csrf-input"]').setValue('changed')
    expect(wrapper.find('[data-testid="cookie-error"]').exists()).toBe(false)
  })
})
