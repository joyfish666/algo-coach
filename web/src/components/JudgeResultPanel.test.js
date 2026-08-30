import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import JudgeResultPanel from './JudgeResultPanel.vue'
import { useI18nStore } from '../stores/i18n'

function mountPanel(verdict) {
  return mount(JudgeResultPanel, {
    props: { verdict },
    global: { plugins: [createPinia()] },
  })
}

describe('JudgeResultPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    useI18nStore().set('zh')
  })

  it('localizes the verdict headline and colors accepted green', () => {
    const wrapper = mountPanel({
      status_key: 'accepted',
      runtime_display: '52 ms',
      memory_display: '41 MB',
      total_correct: 57,
      total_testcases: 57,
    })
    const headline = wrapper.find('.headline')
    expect(headline.text()).toBe('通过')
    expect(headline.classes()).toContain('is-accepted')
  })

  it('maps every failing status to the failure tone', () => {
    for (const key of ['wrong_answer', 'runtime_error', 'compile_error', 'tle', 'mle', 'ole']) {
      const wrapper = mountPanel({ status_key: key })
      expect(wrapper.find('.headline').classes(), key).toContain('is-failed')
      wrapper.unmount()
    }
  })

  it('falls back to the raw server message for unknown keys', () => {
    const wrapper = mountPanel({ status_key: 'weird_new_status', status_msg: 'Odd' })
    expect(wrapper.find('.headline').text()).toBe('Odd')
    expect(wrapper.find('.headline').classes()).toContain('is-unknown')
  })

  it('emits close when the close button is clicked', async () => {
    const wrapper = mountPanel({ status_key: 'accepted' })
    await wrapper.find('[data-testid="judge-result-close"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('hides the case counter when there are zero testcases', () => {
    // "0 / 0" used to render as a meaningless metric row
    const wrapper = mountPanel({
      status_key: 'accepted',
      runtime_display: '40 ms',
      memory_display: '40 MB',
      total_correct: 0,
      total_testcases: 0,
    })
    expect(wrapper.text()).not.toContain('0 / 0')

    const partial = mountPanel({
      status_key: 'wrong_answer',
      runtime_display: '41 ms',
      memory_display: '41 MB',
      total_correct: 30,
      total_testcases: 57,
    })
    expect(partial.text()).toContain('30 / 57')
  })
})
