import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const askMock = vi.fn()

vi.mock('../api', () => ({
  api: {
    ask: (...args) => askMock(...args),
  },
}))

import AiChatSidebar from './AiChatSidebar.vue'

function mountPanel(qid = 'two-sum') {
  return mount(AiChatSidebar, {
    props: { qid },
    global: { plugins: [createPinia()] },
    attachTo: document.body,
  })
}

describe('ai chat sidebar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    document.body.innerHTML = ''
    askMock.mockReset()
  })

  it('clears the conversation when the problem changes', async () => {
    askMock.mockResolvedValue({ answer: '思路：哈希表' })
    const wrapper = mountPanel()
    await wrapper.find('[data-testid="ai-open"]').trigger('click')

    await wrapper.find('textarea').setValue('怎么解？')
    await wrapper.find('button.btn-primary').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.bubble').length).toBe(2)

    await wrapper.setProps({ qid: 'add-two-num' })
    // conversation must not leak into the next problem's context
    expect(wrapper.findAll('.bubble').length).toBe(0)
    expect(wrapper.find('.empty').exists()).toBe(true)
    wrapper.unmount()
  })

  it('does not feed error bubbles back as assistant history', async () => {
    askMock
      .mockRejectedValueOnce(Object.assign(new Error('boom'), { payload: null }))
      .mockResolvedValueOnce({ answer: 'ok' })

    const wrapper = mountPanel()
    await wrapper.find('[data-testid="ai-open"]').trigger('click')

    await wrapper.find('textarea').setValue('first')
    await wrapper.find('button.btn-primary').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.bubble.error').length).toBe(1)

    await wrapper.find('textarea').setValue('second')
    await wrapper.find('button.btn-primary').trigger('click')
    await flushPromises()

    const secondCall = askMock.mock.calls[1][0]
    // only the two real user turns are sent; the error bubble is excluded
    expect(secondCall.history.map((m) => m.role)).toEqual(['user'])
    wrapper.unmount()
  })

  it('drops an in-flight answer when the problem switched mid-request', async () => {
    let resolveAsk
    askMock.mockReturnValue(
      new Promise((resolve) => {
        resolveAsk = resolve
      })
    )

    const wrapper = mountPanel()
    await wrapper.find('[data-testid="ai-open"]').trigger('click')
    await wrapper.find('textarea').setValue('slow question')
    await wrapper.find('button.btn-primary').trigger('click')

    await wrapper.setProps({ qid: 'other-problem' })
    resolveAsk({ answer: 'stale answer' })
    await flushPromises()

    expect(wrapper.findAll('.bubble').length).toBe(0)
    wrapper.unmount()
  })
})
