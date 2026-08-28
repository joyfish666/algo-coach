import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const apiMocks = {
  getProblem: vi.fn(),
  putSolution: vi.fn().mockResolvedValue({ saved: true }),
  judgeRun: vi.fn(),
  judgeSubmit: vi.fn(),
  getTemplate: vi.fn(),
}

vi.mock('../api', () => ({
  api: new Proxy({}, {
    get: (_t, prop) => apiMocks[prop] ?? vi.fn(),
  }),
}))

vi.mock('../snapshots', () => ({
  loadSnapshot: () => null,
  saveSnapshot: () => {},
  snapshotNewerThan: () => false,
}))

vi.mock('vue-router', () => ({
  onBeforeRouteLeave: () => {},
  useRouter: () => ({ push: vi.fn() }),
}))

import ProblemDetail from './ProblemDetail.vue'

const FIXTURE = {
  slug: 'two-sum',
  title_cn: '两数之和',
  title_en: 'Two Sum',
  difficulty: 'easy',
  paid_only: false,
  supported: true,
  tags: [{ slug: 'array', name_zh: '数组', name_en: 'Array' }],
  hints: [],
  languages_available: ['cpp'],
  language: 'cpp',
  code: '// tpl\n',
  testcases: '',
  cases: [],
  solution_mtime: 0,
  statement_markdown: '给定一个整数数组',
}

const raf = () => new Promise((r) => requestAnimationFrame(() => r()))

async function mountWorkbench(localStorageSeed) {
  localStorage.setItem('algocoach-workbench-split', JSON.stringify(localStorageSeed))
  apiMocks.getProblem.mockResolvedValue(JSON.parse(JSON.stringify(FIXTURE)))
  const wrapper = mount(ProblemDetail, {
    props: { qid: 'two-sum' },
    global: {
      plugins: [createPinia()],
      stubs: {
        CodeEditor: { template: '<div class="stub-editor"/>' },
        AiChatSidebar: { template: '<div class="stub-ai"/>' },
        RouterLink: { template: '<a><slot/></a>' },
        Teleport: { template: '<div><slot/></div>' },
      },
    },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

describe('workbench layout', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    document.body.innerHTML = ''
  })

  it('renders the converted statement text', async () => {
    const wrapper = await mountWorkbench({ mainPct: 42, editorPct: 66 })
    expect(wrapper.find('.statement').html()).toContain('给定一个整数数组')
    wrapper.unmount()
  })

  it('loading a problem never re-fires the language-switch flow', async () => {
    // Regression: watchers flush asynchronously, so loadProblem's problem/lang
    // assignments raced the lang watcher's `!problem.value` guard - the mount
    // looked like a user language switch and PUT the just-loaded python3 code
    // under the previous language (silently corrupting an unrelated file),
    // then replaced the editor content with a fresh template.
    apiMocks.getProblem.mockResolvedValue({
      ...JSON.parse(JSON.stringify(FIXTURE)),
      language: 'python3',
      languages_available: ['python3'],
      code: '# saved python work\n',
    })
    apiMocks.putSolution.mockClear()

    const wrapper = mount(ProblemDetail, {
      props: { qid: 'two-sum' },
      global: {
        plugins: [createPinia()],
        stubs: {
          CodeEditor: { template: '<div class="stub-editor"/>' },
          AiChatSidebar: { template: '<div class="stub-ai"/>' },
          RouterLink: { template: '<a><slot/></a>' },
          Teleport: { template: '<div><slot/></div>' },
        },
      },
      attachTo: document.body,
    })
    await flushPromises()
    // one full macrotask later the queued watcher callbacks have flushed too
    await new Promise((resolve) => setTimeout(resolve, 0))
    await flushPromises()

    expect(apiMocks.putSolution).not.toHaveBeenCalled()
    const select = wrapper.find('[data-testid="editor-lang-select"]')
    expect(select.element.value).toBe('python3')
    wrapper.unmount()
  })

  it('left pane width follows persisted ratio', async () => {
    const wrapper = await mountWorkbench({ mainPct: 30, editorPct: 60 })
    const left = wrapper.find('.left-pane')
    expect(left.attributes('style')).toContain('width: 30%')
    wrapper.unmount()
  })

  it('dragging the main divider resizes the left pane and persists', async () => {
    const wrapper = await mountWorkbench({ mainPct: 40, editorPct: 66 })
    const leftEl = wrapper.find('.left-pane').element
    leftEl.getBoundingClientRect = () => ({ left: 0, width: 2000, top: 0, height: 2000 })

    const addSpy = vi.spyOn(document, 'addEventListener')
    await wrapper.find('[data-testid="divider-main"]').trigger('mousedown')
    expect(addSpy).toHaveBeenCalledWith('mousemove', expect.any(Function))
    expect(document.body.style.cursor).toBe('col-resize')

    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 1500, clientY: 0 }))
    await raf()
    await flushPromises()
    expect(wrapper.find('.left-pane').attributes('style')).toContain('width: 75%')

    document.dispatchEvent(new MouseEvent('mouseup'))
    const stored = JSON.parse(localStorage.getItem('algocoach-workbench-split'))
    expect(stored.mainPct).toBeCloseTo(75, 0)
    wrapper.unmount()
  })

  it('dragging the horizontal divider resizes the editor zone', async () => {
    const wrapper = await mountWorkbench({ mainPct: 40, editorPct: 50 })
    const rightEl = wrapper.find('.right-col').element
    rightEl.getBoundingClientRect = () => ({ left: 0, width: 500, top: 0, height: 2000 })

    await wrapper.find('[data-testid="divider-editor"]').trigger('mousedown')
    expect(document.body.style.cursor).toBe('row-resize')

    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 0, clientY: 1600 }))
    await raf()
    await flushPromises()
    expect(wrapper.find('.editor-zone').attributes('style')).toContain('height: 80%')

    document.dispatchEvent(new MouseEvent('mouseup'))
    wrapper.unmount()
  })
})
