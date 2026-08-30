import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const snapshotMocks = vi.hoisted(() => ({
  saveSnapshot: vi.fn(),
}))

// every component along the workbench tree may register route guards; the
// router invokes all of them on navigation, so capture a list
const routerMocks = vi.hoisted(() => ({
  routeLeaveHooks: [],
}))

const apiMocks = {
  getProblem: vi.fn(),
  putSolution: vi.fn().mockResolvedValue({ saved: true }),
  putNotes: vi.fn().mockResolvedValue({ saved: true }),
  putTestcases: vi.fn().mockResolvedValue({ saved: true }),
  putFavorite: vi.fn().mockResolvedValue({ favorite: true }),
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
  saveSnapshot: snapshotMocks.saveSnapshot,
  snapshotNewerThan: () => false,
}))

vi.mock('vue-router', () => ({
  onBeforeRouteLeave: (fn) => {
    routerMocks.routeLeaveHooks.push(fn)
  },
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
  notes: '',
  solution_mtime: 0,
  statement_markdown: '给定一个整数数组',
}

const NEXT_FIXTURE = {
  ...JSON.parse(JSON.stringify(FIXTURE)),
  slug: 'valid-parentheses',
  title_cn: '有效的括号',
  language: 'python3',
  languages_available: ['python3'],
  code: '# next problem\n',
  notes: '# next notes\n',
  testcases: '()\n',
}

const raf = () => new Promise((r) => requestAnimationFrame(() => r()))

// watchers flush asynchronously: one macrotask lets the queued callbacks run
const settleWatchers = async () => {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await flushPromises()
}

async function mountWorkbench(localStorageSeed) {
  localStorage.setItem('algocoach-workbench-split', JSON.stringify(localStorageSeed))
  apiMocks.getProblem.mockResolvedValue(JSON.parse(JSON.stringify(FIXTURE)))
  const wrapper = mount(ProblemDetail, {
    props: { qid: 'two-sum' },
    global: {
      plugins: [createPinia()],
      stubs: {
        CodeEditor: {
          emits: ['update:modelValue'],
          template: '<div class="stub-editor" @click="$emit(\'update:modelValue\', \'// typed\')"/>',
        },
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
    routerMocks.routeLeaveHooks.length = 0
    snapshotMocks.saveSnapshot.mockClear()
    apiMocks.putSolution.mockClear()
    apiMocks.putNotes.mockClear()
    apiMocks.putTestcases.mockClear()
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
          CodeEditor: {
            emits: ['update:modelValue'],
            template: '<div class="stub-editor" @click="$emit(\'update:modelValue\', \'// typed\')"/>',
          },
          AiChatSidebar: { template: '<div class="stub-ai"/>' },
          RouterLink: { template: '<a><slot/></a>' },
          Teleport: { template: '<div><slot/></div>' },
        },
      },
      attachTo: document.body,
    })
    await flushPromises()
    await settleWatchers()

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

  it('dragging the horizontal divider sizes and opens the cases zone', async () => {
    const wrapper = await mountWorkbench({ mainPct: 40, editorPct: 50 })
    const rightEl = wrapper.find('.right-col').element
    rightEl.getBoundingClientRect = () => ({
      left: 0,
      width: 500,
      top: 0,
      height: 2000,
      bottom: 2000,
    })

    await wrapper.find('[data-testid="divider-editor"]').trigger('mousedown')
    expect(document.body.style.cursor).toBe('row-resize')

    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 0, clientY: 1600 }))
    await raf()
    await flushPromises()
    // 2000 - 1600 = 400px of cases height; the editor flexes to the rest and
    // the drag opens the collapsed panel so the handle has visible feedback
    expect(wrapper.find('.cases-zone').attributes('style')).toContain('--cases-h: 400px')
    expect(wrapper.find('[data-testid="cases-input"]').exists()).toBe(true)

    document.dispatchEvent(new MouseEvent('mouseup'))
    wrapper.unmount()
  })
})

describe('workbench persistence contracts', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    document.body.innerHTML = ''
    routerMocks.routeLeaveHooks.length = 0
    snapshotMocks.saveSnapshot.mockClear()
    apiMocks.putSolution.mockClear()
    apiMocks.putNotes.mockClear()
    apiMocks.putTestcases.mockClear()
  })

  it('flushes a pending code autosave under the OLD qid when the problem switches', async () => {
    // Both halves of this contract are load-bearing: flushing with the old
    // qid keeps the last keystrokes; a bare cancel would drop them, and
    // letting the new qid be used would corrupt the next problem's file.
    const wrapper = await mountWorkbench({ mainPct: 42, editorPct: 66 })
    apiMocks.getProblem.mockResolvedValue(JSON.parse(JSON.stringify(NEXT_FIXTURE)))

    await wrapper.find('.stub-editor').trigger('click') // type into the editor
    await wrapper.setProps({ qid: 'valid-parentheses' })
    await settleWatchers()

    expect(apiMocks.putSolution).toHaveBeenCalledWith('two-sum', 'cpp', '// typed')
    expect(apiMocks.putSolution).toHaveBeenCalledTimes(1)
    // the next problem still loads normally afterwards
    expect(wrapper.find('[data-testid="editor-lang-select"]').element.value).toBe('python3')
    wrapper.unmount()
  })

  it('snapshots the draft under the OLD qid when the problem switches', async () => {
    const wrapper = await mountWorkbench({ mainPct: 42, editorPct: 66 })
    apiMocks.getProblem.mockResolvedValue(JSON.parse(JSON.stringify(NEXT_FIXTURE)))

    await wrapper.find('.stub-editor').trigger('click')
    await wrapper.setProps({ qid: 'valid-parentheses' })
    await settleWatchers()

    expect(snapshotMocks.saveSnapshot).toHaveBeenCalledWith('two-sum', 'cpp', '// typed')
    wrapper.unmount()
  })

  it('flushes a pending notes autosave under the OLD qid when the problem switches', async () => {
    const wrapper = await mountWorkbench({ mainPct: 42, editorPct: 66 })
    apiMocks.getProblem.mockResolvedValue(JSON.parse(JSON.stringify(NEXT_FIXTURE)))

    await wrapper.find('[data-testid="notes-open"]').trigger('click')
    await wrapper.find('[data-testid="notes-input"]').setValue('# 我的思路')
    await wrapper.setProps({ qid: 'valid-parentheses' })
    await settleWatchers()

    expect(apiMocks.putNotes).toHaveBeenCalledWith('two-sum', '# 我的思路')
    expect(apiMocks.putNotes).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('adopts the next problem\'s notes after the switch completes', async () => {
    const wrapper = await mountWorkbench({ mainPct: 42, editorPct: 66 })
    apiMocks.getProblem.mockResolvedValue(JSON.parse(JSON.stringify(NEXT_FIXTURE)))

    await wrapper.find('[data-testid="notes-open"]').trigger('click')
    await wrapper.find('[data-testid="notes-input"]').setValue('# 我的思路')
    await wrapper.setProps({ qid: 'valid-parentheses' })
    await settleWatchers()

    expect(wrapper.find('[data-testid="notes-input"]').element.value).toBe('# next notes\n')
    wrapper.unmount()
  })

  it('flushes a pending notes autosave on route leave', async () => {
    const wrapper = await mountWorkbench({ mainPct: 42, editorPct: 66 })
    await wrapper.find('[data-testid="notes-open"]').trigger('click')
    await wrapper.find('[data-testid="notes-input"]').setValue('# 离开前最后的想法')

    expect(routerMocks.routeLeaveHooks.length).toBeGreaterThan(0)
    routerMocks.routeLeaveHooks.forEach((hook) => hook(undefined, undefined, () => {}))
    expect(apiMocks.putNotes).toHaveBeenCalledWith('two-sum', '# 离开前最后的想法')
    wrapper.unmount()
  })

  it('saves the cases draft through the testcases endpoint', async () => {
    const wrapper = await mountWorkbench({ mainPct: 42, editorPct: 66 })

    await wrapper.find('[data-testid="cases-input"]').setValue('1 2\n3')
    await wrapper.find('[data-testid="cases-save"]').trigger('click')
    await flushPromises()

    expect(apiMocks.putTestcases).toHaveBeenCalledWith('two-sum', '1 2\n3')
    expect(wrapper.find('[data-testid="cases-saved"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows the judging indicator while a run is in flight and hides it after', async () => {
    let resolveRun
    apiMocks.judgeRun.mockImplementation(
      () => new Promise((resolve) => { resolveRun = resolve })
    )
    const wrapper = await mountWorkbench({ mainPct: 42, editorPct: 66 })

    await wrapper.find('[data-testid="run-btn"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="judging-indicator"]').exists()).toBe(true)

    resolveRun({ status_key: 'accepted', mode: 'run' })
    await flushPromises()
    expect(wrapper.find('[data-testid="judging-indicator"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
