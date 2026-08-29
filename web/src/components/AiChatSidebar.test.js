import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import { useStatusStore } from '../stores/status'

const askMock = vi.fn()

vi.mock('../api', () => ({
  api: {
    ask: (...args) => askMock(...args),
    getStatus: () => Promise.resolve({ llm_configured: true }),
  },
}))

import AiChatSidebar from './AiChatSidebar.vue'

let pinia

function mountPanel(qid = 'two-sum', extraProps = {}) {
  return mount(AiChatSidebar, {
    props: { qid, ...extraProps },
    global: {
      plugins: [pinia],
      stubs: { RouterLink: { template: '<a><slot/></a>' } },
    },
    attachTo: document.body,
  })
}

describe('ai chat sidebar', () => {
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    localStorage.clear()
    document.body.innerHTML = ''
    askMock.mockReset()
    // most tests exercise the configured path; the not-configured gate has
    // its own test below. Marking the store loaded keeps the component from
    // re-fetching status on mount and overwriting the seeded value.
    Object.assign(useStatusStore(), { loaded: true, llmConfigured: true })
  })

  it('clears the conversation via the header button and disables itself when empty', async () => {
    askMock.mockResolvedValue({ answer: '思路：哈希表' })
    const wrapper = mountPanel()
    await wrapper.find('[data-testid="ai-open"]').trigger('click')

    // nothing to clear yet
    expect(wrapper.find('[data-testid="ai-clear"]').attributes('disabled')).toBeDefined()

    await wrapper.find('textarea').setValue('怎么解？')
    await wrapper.find('button.btn-primary').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.bubble').length).toBe(2)

    await wrapper.find('[data-testid="ai-clear"]').trigger('click')
    expect(wrapper.findAll('.bubble').length).toBe(0)
    expect(wrapper.find('.empty').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-clear"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
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

  it('does not send while an IME composition is being confirmed', async () => {
    // Chinese input commits candidates with Enter; that Enter must not send
    askMock.mockResolvedValue({ answer: 'nope' })
    const wrapper = mountPanel()
    await wrapper.find('[data-testid="ai-open"]').trigger('click')
    await wrapper.find('textarea').setValue('pinyin draft')

    const fireKeydown = (isComposing) => {
      const event = new KeyboardEvent('keydown', { key: 'Enter', cancelable: true })
      // isComposing is a prototype getter; define an own property to simulate
      Object.defineProperty(event, 'isComposing', { value: isComposing })
      wrapper.find('textarea').element.dispatchEvent(event)
      return event.defaultPrevented
    }

    expect(fireKeydown(true)).toBe(false) // composition Enter: ignored outright
    expect(askMock).not.toHaveBeenCalled()
    expect(wrapper.find('textarea').element.value).toBe('pinyin draft')

    expect(fireKeydown(false)).toBe(true) // normal Enter: sent + preventDefault
    expect(askMock).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('closes on Escape and re-clamps a restored off-screen position on resize', async () => {
    localStorage.setItem(
      'algocoach-ai-pos',
      JSON.stringify({ x: 50, y: window.innerHeight + 400 })
    )
    const wrapper = mountPanel()

    // opening re-clamps the stale position back into the viewport
    await wrapper.find('[data-testid="ai-open"]').trigger('click')
    const panel = wrapper.find('[data-testid="ai-panel"]')
    expect(panel.exists()).toBe(true)
    const top = Number.parseInt(panel.attributes('style').match(/top: (\d+)px/)[1], 10)
    expect(top).toBeLessThan(window.innerHeight)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[data-testid="ai-panel"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('gates sending behind an LLM-not-configured hint pointing at Settings', async () => {
    // the workbench used to be the only LLM surface without a not-configured
    // gate: users discovered the missing key from an error bubble per send
    Object.assign(useStatusStore(), { loaded: true, llmConfigured: false })
    const wrapper = mountPanel()
    await wrapper.find('[data-testid="ai-open"]').trigger('click')

    expect(wrapper.find('[data-testid="ai-not-configured"]').exists()).toBe(true)

    await wrapper.find('textarea').setValue('怎么解？')
    await wrapper.find('[data-testid="ai-send"]').trigger('click')
    await flushPromises()
    expect(askMock).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('renders assistant replies as markdown but keeps user text verbatim', async () => {
    // LLM output IS markdown: plain-text interpolation leaked "**bold**"
    // markers into the chat (the analytics report already rendered - the chat
    // bubble was the inconsistent surface)
    askMock.mockResolvedValue({ answer: '先想**思路**：\n\n- 哈希表' })
    const wrapper = mountPanel()
    await wrapper.find('[data-testid="ai-open"]').trigger('click')

    await wrapper.find('textarea').setValue('my **draft** stays')
    await wrapper.find('[data-testid="ai-send"]').trigger('click')
    await flushPromises()

    const bubbles = wrapper.findAll('.bubble')
    expect(bubbles).toHaveLength(2)
    expect(bubbles[1].find('.md strong').exists()).toBe(true)
    expect(bubbles[1].text()).not.toContain('**')
    expect(bubbles[1].find('.md li').text()).toBe('哈希表')
    // the user's own draft is not markdown-rendered
    expect(bubbles[0].text()).toContain('**')
    // history fed back to the LLM keeps the raw markdown text, not the html
    expect(askMock.mock.calls[0][0].question).toBe('my **draft** stays')
    wrapper.unmount()
  })

  it('labels the attached-code language instead of the old null', async () => {
    // the editor language is known here; sending it lets the backend phrase
    // the context as "Current code (python3):" instead of "(text)".
    // ui_lang itself is attached in the api layer and asserted in api.test.js
    askMock.mockResolvedValue({ answer: 'ok' })
    const wrapper = mountPanel('two-sum', { codeLang: 'python3' })
    await wrapper.find('[data-testid="ai-open"]').trigger('click')

    await wrapper.find('textarea').setValue('why TLE?')
    await wrapper.find('button.btn-primary').trigger('click')
    await flushPromises()

    expect(askMock.mock.calls[0][0].lang).toBe('python3')
    wrapper.unmount()
  })
})
