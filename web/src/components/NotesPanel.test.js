import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'

const apiMocks = {
  putNotes: vi.fn().mockResolvedValue({ saved: true }),
  getStatus: vi.fn().mockResolvedValue({ llm_configured: true }),
}

vi.mock('../api', () => ({
  api: new Proxy({}, {
    get: (_t, prop) => apiMocks[prop] ?? vi.fn(),
  }),
}))

vi.mock('vue-router', () => ({
  onBeforeRouteLeave: vi.fn(),
}))

import AiChatSidebar from './AiChatSidebar.vue'
import NotesPanel from './NotesPanel.vue'
import { activeFloatingPanel } from '../utils/floatingPanel'
import { useStatusStore } from '../stores/status'

function mountPair() {
  const wrapper = mount(
    {
      components: { AiChatSidebar, NotesPanel },
      template: '<div><AiChatSidebar qid="two-sum"/><NotesPanel qid="two-sum" notes=""/></div>',
    },
    {
      attachTo: document.body,
      global: {
        plugins: [createPinia()],
        // the status store must not refetch on mount and wipe the default
        stubs: { RouterLink: { template: '<a><slot/></a>' } },
      },
    }
  )
  return wrapper
}

describe('floating workbench panels', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    document.body.innerHTML = ''
    apiMocks.putNotes.mockClear()
    apiMocks.getStatus.mockClear()
    // the AI sidebar reads LLM availability on mount; seeding the store keeps
    // it from refetching and matches the configured-path default
    Object.assign(useStatusStore(), { loaded: true, llmConfigured: true })
    activeFloatingPanel.value = null
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('opens the notes panel from the circular button and closes on Escape', async () => {
    const wrapper = mountPair()

    expect(wrapper.find('[data-testid="notes-panel"]').exists()).toBe(false)
    await wrapper.find('[data-testid="notes-open"]').trigger('click')
    expect(wrapper.find('[data-testid="notes-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="notes-open"]').attributes('aria-pressed')).toBe('true')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[data-testid="notes-panel"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('closes the AI panel when the notes panel opens (shared corner, one at a time)', async () => {
    const wrapper = mountPair()

    await wrapper.find('[data-testid="ai-open"]').trigger('click')
    expect(wrapper.find('[data-testid="ai-panel"]').exists()).toBe(true)

    await wrapper.find('[data-testid="notes-open"]').trigger('click')
    expect(wrapper.find('[data-testid="notes-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-panel"]').exists()).toBe(false)

    await wrapper.find('[data-testid="ai-open"]').trigger('click')
    expect(wrapper.find('[data-testid="ai-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="notes-panel"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('autosaves the notes draft after the debounce elapses', async () => {
    vi.useFakeTimers()
    const wrapper = mountPair()

    await wrapper.find('[data-testid="notes-open"]').trigger('click')
    await wrapper.find('[data-testid="notes-input"]').setValue('# 思路')
    expect(apiMocks.putNotes).not.toHaveBeenCalled()

    vi.advanceTimersByTime(1300)
    await flushPromises()
    expect(apiMocks.putNotes).toHaveBeenCalledWith('two-sum', '# 思路')
    expect(wrapper.find('[data-testid="notes-saved"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
