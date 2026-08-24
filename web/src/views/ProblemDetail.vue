<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import MarkdownIt from 'markdown-it'

import CodeEditor from '../components/CodeEditor.vue'
import AiChatSidebar from '../components/AiChatSidebar.vue'
import JudgeResultPanel from '../components/JudgeResultPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import { api } from '../api'
import { useI18nStore } from '../stores/i18n'
import { loadSnapshot, saveSnapshot, snapshotNewerThan } from '../snapshots'

const props = defineProps({ qid: { type: String, required: true } })

const i18n = useI18nStore()

const md = new MarkdownIt({ html: false, linkify: false, breaks: false })

const SPLIT_KEY = 'algocoach-workbench-split'

const loading = ref(true)
const errorText = ref('')
const problem = ref(null)
const code = ref('')
const lang = ref('cpp')
const languages = [
  { value: 'cpp', label: 'C++' },
  { value: 'python3', label: 'Python 3' },
  { value: 'java', label: 'Java' },
]
const switchingLang = ref(false)
const statementHtml = ref('')
const renderedStatement = computed(() => statementHtml.value)

const useLocalCases = ref(false)
const casesOpen = ref(true)
const casesDraft = ref('')
const casesSaving = ref(false)
const casesSavedAt = ref('')

const inflightRun = ref(false)
const inflightSubmit = ref(false)
const verdict = ref(null)

const judgingActive = ref(false)
const judgingSeconds = ref(0)
let judgingTimer = null

function startJudgingIndicator() {
  judgingActive.value = true
  judgingSeconds.value = 0
  clearInterval(judgingTimer)
  judgingTimer = setInterval(() => (judgingSeconds.value += 1), 1000)
}

function stopJudgingIndicator() {
  judgingActive.value = false
  clearInterval(judgingTimer)
  judgingTimer = null
}

const restoreCandidate = ref(null)
const showRestoreBar = ref(false)

let autosaveTimer = null

const leftPaneRef = ref(null)
const rightColRef = ref(null)
const dragActive = ref(false)

function readSplit() {
  try {
    const raw = JSON.parse(localStorage.getItem(SPLIT_KEY))
    if (raw && typeof raw.mainPct === 'number' && typeof raw.editorPct === 'number') return raw
  } catch {
  }
  return { mainPct: 42, editorPct: 66 }
}

const split = ref(readSplit())

function persistSplit() {
  try {
    localStorage.setItem(SPLIT_KEY, JSON.stringify(split.value))
  } catch {
  }
}

let dragContext = null
let rafId = 0
let pendingEvent = null

function onMouseMove(event) {
  pendingEvent = event
  if (rafId) return
  rafId = requestAnimationFrame(applyDrag)
}

function applyDrag() {
  rafId = 0
  const event = pendingEvent
  if (!dragContext || !event) return
  if (dragContext.axis === 'x') {
    const rect = leftPaneRef.value?.getBoundingClientRect()
    if (!rect) return
    const total = rect.width / (split.value.mainPct / 100)
    const minPct = (280 / total) * 100
    const maxPct = 100 - (320 / total) * 100
    split.value.mainPct = Math.min(
      Math.max(minPct, ((event.clientX - rect.left) / rect.width) * 100),
      maxPct
    )
  } else {
    const rect = rightColRef.value?.getBoundingClientRect()
    if (!rect) return
    const minEditor = (220 / rect.height) * 100
    const maxEditor = 100 - (150 / rect.height) * 100
    split.value.editorPct = Math.min(
      Math.max(minEditor, ((event.clientY - rect.top) / rect.height) * 100),
      maxEditor
    )
  }
}

function onMouseUp() {
  dragContext = null
  dragActive.value = false
  if (rafId) {
    cancelAnimationFrame(rafId)
    rafId = 0
  }
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', onMouseUp)
  persistSplit()
}

function startDrag(axis, event) {
  event.preventDefault()
  dragContext = { axis }
  dragActive.value = true
  document.body.style.cursor = axis === 'x' ? 'col-resize' : 'row-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

onBeforeUnmount(() => {
  onMouseUp()
})

const languageOptions = computed(() =>
  languages.map((item) => ({
    ...item,
    missing: problem.value ? !problem.value.languages_available.includes(item.value) : false,
  }))
)

async function loadProblem() {
  const qidAtStart = props.qid
  loading.value = true
  errorText.value = ''
  verdict.value = null
  try {
    const data = await api.getProblem(props.qid)
    if (props.qid !== qidAtStart) return // a newer navigation superseded us
    problem.value = data
    lang.value =
      data.language && languages.some((l) => l.value === data.language)
        ? data.language
        : data.languages_available[0] || 'cpp'
    code.value = data.code || ''
    casesDraft.value = data.testcases || ''
    statementHtml.value = md.render(data.statement_markdown || '')

    const snap = loadSnapshot(props.qid, lang.value)
    if (
      snap &&
      snap.c !== code.value &&
      snapshotNewerThan(snap, data.solution_mtime || 0)
    ) {
      restoreCandidate.value = snap
      showRestoreBar.value = true
    }
  } catch (err) {
    if (props.qid !== qidAtStart) return
    applyError(err)
  } finally {
    if (props.qid === qidAtStart) loading.value = false
  }
}

function applyError(err) {
  const keyFromServer =
    err && err.payload && err.payload.error && err.payload.error.message_key
  if (keyFromServer) {
    const translated = i18n.t(keyFromServer)
    errorText.value = translated !== keyFromServer ? translated : keyFromServer
    const detail = err.payload?.error?.detail
    if (detail && detail.last_poll) {
      try {
        errorText.value +=
          '\n' + JSON.stringify(detail.last_poll).slice(0, 400)
      } catch {
      }
    }
    return
  }
  if (err && err.status === 403) {
    errorText.value = i18n.t('premium_problem')
    return
  }
  errorText.value = (err && err.message) || 'error'
}

function scheduleAutosave() {
  clearTimeout(autosaveTimer)
  autosaveTimer = setTimeout(flushSave, 1200)
}

async function flushSave() {
  clearTimeout(autosaveTimer)
  autosaveTimer = null
  try {
    await api.putSolution(props.qid, lang.value, code.value)
  } catch {
    /* offline or transient; snapshot keeps the draft */
  }
}

watch(code, (value) => {
  saveSnapshot(props.qid, lang.value, value)
  scheduleAutosave()
})

watch(lang, async (_next, prev) => {
  if (!problem.value || switchingLang.value) return
  switchingLang.value = true
  clearTimeout(autosaveTimer)
  try {
    await api.putSolution(props.qid, prev, code.value)
  } catch {
  }
  try {
    const result = await api.getTemplate(props.qid, _next)
    lang.value = _next
    code.value = result.code || ''
    if (!problem.value.languages_available.includes(_next)) {
      problem.value.languages_available.push(_next)
    }
  } catch (err) {
    applyError(err)
    lang.value = prev
  } finally {
    switchingLang.value = false
  }
})

async function restoreDraft() {
  if (!restoreCandidate.value) return
  code.value = restoreCandidate.value.c
  showRestoreBar.value = false
  await flushSave()
}

function discardDraft() {
  saveSnapshot(props.qid, lang.value, code.value)
  showRestoreBar.value = false
}

async function saveCases() {
  casesSaving.value = true
  try {
    await api.putTestcases(props.qid, casesDraft.value)
    casesSavedAt.value = new Date().toLocaleTimeString()
  } catch (err) {
    applyError(err)
  } finally {
    casesSaving.value = false
  }
}

async function runCode() {
  if (inflightRun.value) return
  inflightRun.value = true
  verdict.value = null
  errorText.value = ''
  clearTimeout(autosaveTimer)
  startJudgingIndicator()
  try {
    await api.putSolution(props.qid, lang.value, code.value)
    verdict.value = await api.judgeRun({
      qid: props.qid,
      lang: lang.value,
      code: code.value,
      use_local: useLocalCases.value,
    })
  } catch (err) {
    applyError(err)
  } finally {
    inflightRun.value = false
    stopJudgingIndicator()
  }
}

async function submitCode() {
  if (inflightSubmit.value) return
  inflightSubmit.value = true
  verdict.value = null
  errorText.value = ''
  clearTimeout(autosaveTimer)
  startJudgingIndicator()
  try {
    await api.putSolution(props.qid, lang.value, code.value)
    verdict.value = await api.judgeSubmit({
      qid: props.qid,
      lang: lang.value,
      code: code.value,
    })
  } catch (err) {
    applyError(err)
  } finally {
    inflightSubmit.value = false
    stopJudgingIndicator()
  }
}

// Ctrl+Enter runs, Ctrl+Shift+Enter submits - the workbench's primary loop
// should not require leaving the keyboard
function onKeydown(event) {
  if (!(event.ctrlKey || event.metaKey) || event.key !== 'Enter') return
  if (!problem.value || errorText.value) return
  event.preventDefault()
  if (event.shiftKey) submitCode()
  else runCode()
}

onBeforeRouteLeave(() => {
  if (autosaveTimer) {
    flushSave()
  }
  saveSnapshot(props.qid, lang.value, code.value)
})

function onBeforeUnload() {
  saveSnapshot(props.qid, lang.value, code.value)
}

onMounted(() => {
  window.addEventListener('beforeunload', onBeforeUnload)
  window.addEventListener('keydown', onKeydown)
  loadProblem()
})

// vue-router reuses this component on param-only changes, so /problem/a ->
// /problem/b fires beforeRouteUpdate (not Leave) and never remounts; reload
// explicitly or problem A's statement stays under B's URL
watch(
  () => props.qid,
  (next, prev) => {
    if (!next || !prev || next === prev) return
    // pending debounced save must not land under the new qid
    clearTimeout(autosaveTimer)
    autosaveTimer = null
    saveSnapshot(prev, lang.value, code.value)
    verdict.value = null
    errorText.value = ''
    showRestoreBar.value = false
    restoreCandidate.value = null
    statementHtml.value = ''
    stopJudgingIndicator()
    loadProblem()
  }
)

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('keydown', onKeydown)
  clearTimeout(autosaveTimer)
  stopJudgingIndicator()
})
</script>

<template>
  <section class="page page-wide">
    <div v-if="loading" class="card empty-state">{{ i18n.t('loading_problem') }}</div>

    <template v-else-if="errorText">
      <div class="card empty-state" data-testid="workbench-error">
        <p>{{ errorText }}</p>
        <button class="btn btn-ghost" type="button" @click="loadProblem">
          {{ i18n.t('retry') }}
        </button>
      </div>
    </template>

    <template v-else-if="problem">
      <div v-if="problem.supported === false" class="card banner-warn" data-testid="unsupported-banner">
        {{ i18n.t('unsupported_problem') }}
      </div>

      <div v-if="showRestoreBar" class="card banner-accent" data-testid="restore-bar">
        <span>{{ i18n.t('restore_draft') }}</span>
        <button class="btn btn-primary btn-sm" type="button" @click="restoreDraft">
          {{ i18n.t('restore') }}
        </button>
        <button class="btn btn-ghost btn-sm" type="button" @click="discardDraft">
          {{ i18n.t('discard_draft') }}
        </button>
      </div>

      <PageHeader :title="problem.title_cn || problem.title_en || problem.slug">
        <template #subtitle>
          <span class="meta-row">
            <RouterLink
              v-if="problem.difficulty"
              class="chip chip-link"
              :to="{ path: '/problems', query: { difficulty: problem.difficulty } }"
            >
              {{ problem.difficulty }}
            </RouterLink>
            <span v-if="problem.paid_only" class="chip">★</span>
            <RouterLink
              v-for="tag in (problem.tags || []).slice(0, 6)"
              :key="tag.slug"
              class="chip chip-link"
              :to="{ path: '/problems', query: { tag: tag.slug } }"
            >
              {{ tag.name_zh || tag.name_en }}
            </RouterLink>
            <code class="slug-code">#{{ problem.slug }}</code>
          </span>
        </template>
      </PageHeader>

      <div class="wb" :class="{ 'wb-dragging': dragActive }" data-testid="workbench">
        <section ref="leftPaneRef" class="pane left-pane" :style="{ width: split.mainPct + '%' }">
          <div class="card pane-card">
            <h2>{{ i18n.t('problem_statement') }}</h2>
            <div class="statement" v-html="renderedStatement"></div>
          </div>
          <details v-if="(problem.hints || []).length" class="card hints-card">
            <summary>{{ (problem.hints || []).length }} × hint</summary>
            <ul>
              <li v-for="(hint, index) in problem.hints" :key="index">{{ hint }}</li>
            </ul>
          </details>
        </section>

        <div
          class="divider divider-v"
          data-testid="divider-main"
          @mousedown="startDrag('x', $event)"
        ></div>

        <section ref="rightColRef" class="pane right-col">
          <div class="editor-zone" :style="{ height: split.editorPct + '%' }">
            <div class="card editor-card">
              <div class="editor-head">
                <h2>{{ i18n.t('problem_editor') }}</h2>
                <select
                  v-model="lang"
                  class="select"
                  :disabled="switchingLang"
                  data-testid="editor-lang-select"
                >
                  <option v-for="item in languageOptions" :key="item.value" :value="item.value">
                    {{ item.label }}{{ item.missing ? ` · ${i18n.t('lang_missing')}` : '' }}
                  </option>
                </select>
              </div>
              <div class="editor-body">
                <CodeEditor v-model="code" :lang="lang" />
              </div>
              <div class="actions-row">
                <label class="use-local">
                  <input v-model="useLocalCases" type="checkbox" data-testid="use-local-cases" />
                  <span>{{ i18n.t('use_local_cases') }}</span>
                </label>
                <span class="spacer"></span>
                <button
                  class="btn btn-ghost"
                  type="button"
                  :disabled="inflightRun"
                  title="Ctrl+Enter"
                  data-testid="run-btn"
                  @click="runCode"
                >
                  {{ i18n.t('run') }}
                </button>
                <button
                  class="btn btn-primary"
                  type="button"
                  :disabled="inflightSubmit"
                  title="Ctrl+Shift+Enter"
                  data-testid="submit-btn"
                  @click="submitCode"
                >
                  {{ i18n.t('submit') }}
                </button>
              </div>
            </div>
          </div>

          <div
            class="divider divider-h"
            data-testid="divider-editor"
            @mousedown="startDrag('y', $event)"
          ></div>

          <div class="cases-zone">
            <details class="card cases-card" :open="casesOpen" @toggle="casesOpen = $event.target.open">
              <summary>{{ i18n.t('custom_cases') }}</summary>
              <p class="hint-text">{{ i18n.t('custom_cases_hint') }}</p>
              <textarea
                v-model="casesDraft"
                class="input cases-input mono"
                rows="5"
                spellcheck="false"
                data-testid="cases-input"
              ></textarea>
              <div class="actions-row">
                <button
                  class="btn btn-primary"
                  type="button"
                  :disabled="casesSaving"
                  @click="saveCases"
                >
                  {{ i18n.t('save_cases') }}
                </button>
                <span v-if="casesSavedAt" class="saved-hint">{{ i18n.t('cases_saved') }} · {{ casesSavedAt }}</span>
              </div>
            </details>
          </div>
        </section>
      </div>

      <div v-if="judgingActive" class="card judging-card" data-testid="judging-indicator">
        <span class="judging-dot"></span>
        <span>{{ i18n.t('judging_in_progress') }}</span>
        <span class="judging-seconds">{{ judgingSeconds }}s</span>
        <span v-if="inflightSubmit" class="hint-text">{{ i18n.t('judging_submit_hint') }}</span>
      </div>

      <JudgeResultPanel v-if="verdict" :verdict="verdict" />
    </template>

    <AiChatSidebar v-if="problem && problem.supported !== false" :qid="problem.slug || props.qid" />
  </section>
</template>

<style scoped>
.page-wide {
  max-width: none;
}

.banner-warn,
.banner-accent {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  padding: var(--space-4);
}

.banner-accent {
  border-color: var(--accent);
}

.meta-row {
  align-items: center;
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.chip-link:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.slug-code {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
}

.wb {
  display: flex;
  gap: 0;
  min-height: calc(100vh - 220px);
}

.wb-dragging * {
  pointer-events: none;
}

.wb-dragging .divider {
  pointer-events: auto;
}

.pane {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
  min-height: 0;
}

.left-pane {
  padding-right: var(--space-3);
}

.right-col {
  flex: 1;
  padding-left: var(--space-3);
}

.divider {
  background: transparent;
  border-radius: var(--radius-pill);
  flex-shrink: 0;
  position: relative;
  transition: background-color 0.15s ease;
  z-index: 5;
}

.divider-v {
  border-left: 1px solid var(--border-subtle);
  cursor: col-resize;
  margin: 0 calc(var(--space-2) * -1);
  width: calc(var(--space-2) * 2);
}

.divider-h {
  border-top: 1px solid var(--border-subtle);
  cursor: row-resize;
  margin: calc(var(--space-2) * -1) 0;
  height: calc(var(--space-2) * 2);
}

.divider:hover,
.divider:active {
  background: var(--accent);
}

.pane-card,
.hints-card,
.editor-card,
.cases-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.statement {
  overflow-y: auto;
  text-align: left;
}

.statement :deep(p) {
  margin: var(--space-3) 0;
  text-align: left;
}

.statement :deep(pre) {
  background: var(--bg-secondary);
  border-radius: var(--radius-card);
  overflow-x: auto;
  padding: var(--space-3) var(--space-4);
}

.statement :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--font-size-caption);
}

.statement :deep(img) {
  max-width: 100%;
}

.hints-card summary {
  color: var(--gray-neutral);
  cursor: pointer;
}

.hints-card ul {
  margin: var(--space-3) 0 0;
  padding-left: var(--space-6);
}

.editor-zone {
  display: flex;
  flex-direction: column;
  min-height: 180px;
}

.editor-card {
  flex: 1;
}

.editor-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

.editor-body :deep(.code-editor) {
  flex: 1;
  height: 100%;
}

.editor-body :deep(.cm-editor) {
  height: 100%;
}

.editor-body :deep(.cm-scroller) {
  overflow: auto;
}

.editor-head {
  align-items: center;
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}

.editor-head h2 {
  margin-bottom: 0;
}

.actions-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-top: var(--space-3);
}

.spacer {
  flex: 1;
}

.use-local {
  align-items: center;
  color: var(--gray-neutral);
  display: inline-flex;
  font-size: var(--font-size-caption);
  gap: var(--space-1);
}

.btn-sm {
  padding: var(--space-1) var(--space-4);
}

.cases-zone {
  display: flex;
  flex-direction: column;
  min-height: 140px;
}

.cases-card summary {
  color: var(--gray-neutral);
  cursor: pointer;
}

.hint-text {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  margin: var(--space-3) 0;
}

.cases-input {
  width: 100%;
}

.saved-hint {
  color: var(--accent);
  font-size: var(--font-size-caption);
}

.judging-card {
  align-items: center;
  color: var(--text-primary);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-4);
}

.judging-dot {
  animation: judging-pulse 1s infinite;
  background: var(--accent);
  border-radius: 50%;
  display: inline-block;
  height: 8px;
  width: 8px;
}

.judging-seconds {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  min-width: 3ch;
}

@keyframes judging-pulse {
  50% {
    opacity: 0.3;
  }
}
</style>
