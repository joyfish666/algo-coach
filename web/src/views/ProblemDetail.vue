<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import MarkdownIt from 'markdown-it'

import CodeEditor from '../components/CodeEditor.vue'
import AiChatSidebar from '../components/AiChatSidebar.vue'
import JudgeResultPanel from '../components/JudgeResultPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import { api } from '../api'
import { useI18nStore } from '../stores/i18n'
import { useToastStore } from '../stores/toast'
import { loadSnapshot, saveSnapshot, snapshotNewerThan } from '../snapshots'

const props = defineProps({ qid: { type: String, required: true } })

const i18n = useI18nStore()
const toast = useToastStore()

const md = new MarkdownIt({ html: false, linkify: false, breaks: false })

const SPLIT_KEY = 'algocoach-workbench-split'

const loading = ref(true)
// fatal: the problem itself could not be loaded, the whole workbench cannot
// render. Transient action failures (autosave, run, submit) must NOT land
// here - one flaky PUT used to tear down the entire editor surface.
const loadError = ref('')
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

const notesDraft = ref('')
const notesSavedAt = ref('')
let notesTimer = null

const favorite = ref(false)

// difficulty enums render localized like everywhere else (the workbench
// header used to show a raw "medium" in the zh UI); unknown values fall
// back to the raw enum instead of an empty chip
function difficultyLabel(value) {
  const level = (value || '').toLowerCase()
  return ['easy', 'medium', 'hard'].includes(level) ? i18n.t(`diff_${level}`) : value
}

function errorMessageFor(err) {
  const keyFromServer = err && err.payload && err.payload.error && err.payload.error.message_key
  if (keyFromServer) {
    const translated = i18n.t(keyFromServer)
    if (translated !== keyFromServer) return translated
  }
  if (err && err.status === 403) return i18n.t('premium_problem')
  return (err && err.message) || 'error'
}

// transient failures surface as toasts; the workbench stays alive and the
// user keeps their in-progress code visible
function notifyActionError(err) {
  toast.error({ text: errorMessageFor(err) })
}

const inflightRun = ref(false)
const inflightSubmit = ref(false)
// Run and Submit share one verdict surface: letting them race meant the
// slower request overwrote the newer result and the timer indicator was
// switched off by whichever finished first. One gate excludes both, and
// both are excluded while a language switch has code/lang temporarily
// out of sync.
const judgingBusy = computed(
  () => inflightRun.value || inflightSubmit.value || switchingLang.value
)
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
let snapshotTimer = null
// Watchers flush asynchronously, so programmatic assignments (loading a
// problem, applying a fetched template, reverting a failed language switch)
// must be fenced until after the next tick. Without this fence the lang
// watcher treated the loaded problem as a user-initiated switch and PUT the
// just-loaded code under the PREVIOUS language - silently overwriting the
// saved solution of an unrelated problem on every navigation.
let hydrating = false

async function setHydratingUntilFlushed() {
  await nextTick()
  hydrating = false
}

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
  loadError.value = ''
  verdict.value = null
  hydrating = true
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
    notesDraft.value = data.notes || ''
    favorite.value = Boolean(data.favorite)
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
    applyLoadError(err)
  } finally {
    if (props.qid === qidAtStart) {
      loading.value = false
      // hold the fence until queued watcher callbacks have flushed
      await setHydratingUntilFlushed()
    }
  }
}

function applyLoadError(err) {
  loadError.value = errorMessageFor(err)
  const detail = err && err.payload && err.payload.error && err.payload.error.detail
  if (detail && detail.last_poll) {
    try {
      loadError.value += '\n' + JSON.stringify(detail.last_poll).slice(0, 400)
    } catch {
    }
  }
}

function scheduleAutosave() {
  clearTimeout(autosaveTimer)
  autosaveTimer = setTimeout(flushSave, 1200)
}

async function flushSave(qid = props.qid) {
  clearTimeout(autosaveTimer)
  autosaveTimer = null
  try {
    await api.putSolution(qid, lang.value, code.value)
  } catch {
    /* offline or transient; snapshot keeps the draft */
  }
}

// localStorage writes on every keystroke serialized the full snapshot and
// rewrote the index twice per keypress - perceptible on long solutions, so
// the write is debounced like the network save (flushes below cover leave,
// unload and problem switches)
function scheduleSnapshot() {
  clearTimeout(snapshotTimer)
  snapshotTimer = setTimeout(() => {
    snapshotTimer = null
    saveSnapshot(props.qid, lang.value, code.value)
  }, 300)
}

function writeSnapshotNow() {
  clearTimeout(snapshotTimer)
  snapshotTimer = null
  saveSnapshot(props.qid, lang.value, code.value)
}

watch(code, () => {
  if (hydrating) return
  scheduleSnapshot()
  scheduleAutosave()
})

watch(lang, async (_next, prev) => {
  if (!problem.value || switchingLang.value || hydrating) return
  switchingLang.value = true
  clearTimeout(autosaveTimer)
  try {
    await api.putSolution(props.qid, prev, code.value)
  } catch {
  }
  try {
    const result = await api.getTemplate(props.qid, _next)
    hydrating = true
    lang.value = _next
    code.value = result.code || ''
    if (!problem.value.languages_available.includes(_next)) {
      problem.value.languages_available.push(_next)
    }
    await setHydratingUntilFlushed()
  } catch (err) {
    notifyActionError(err)
    // reverting the select is programmatic: without the fence the watcher
    // re-entered and PUT the current (previous-language) code under the
    // language whose template fetch had just failed
    hydrating = true
    lang.value = prev
    await setHydratingUntilFlushed()
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
    notifyActionError(err)
  } finally {
    casesSaving.value = false
  }
}

function scheduleNotesSave() {
  clearTimeout(notesTimer)
  notesTimer = setTimeout(flushNotesSave, 1200)
}

async function flushNotesSave(qid = props.qid) {
  clearTimeout(notesTimer)
  notesTimer = null
  try {
    await api.putNotes(qid, notesDraft.value)
    notesSavedAt.value = new Date().toLocaleTimeString()
  } catch {
    /* transient; the user can retry by editing again */
  }
}

watch(notesDraft, () => scheduleNotesSave())

async function toggleFavorite() {
  const next = !favorite.value
  favorite.value = next
  try {
    await api.putFavorite(props.qid, next)
  } catch (err) {
    favorite.value = !next
    notifyActionError(err)
  }
}

async function runCode() {
  if (judgingBusy.value) return
  inflightRun.value = true
  verdict.value = null
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
    notifyActionError(err)
  } finally {
    inflightRun.value = false
    stopJudgingIndicator()
  }
}

async function submitCode() {
  if (judgingBusy.value) return
  inflightSubmit.value = true
  verdict.value = null
  clearTimeout(autosaveTimer)
  startJudgingIndicator()
  try {
    await api.putSolution(props.qid, lang.value, code.value)
    verdict.value = await api.judgeSubmit({
      qid: props.qid,
      lang: lang.value,
      code: code.value,
    })
    // the submit succeeded server-side but its local archive write failed:
    // without this hint the submission silently never appears in /history
    if (verdict.value && verdict.value.archived === false) {
      toast.error({ text: i18n.t('archive_failed') })
    }
  } catch (err) {
    notifyActionError(err)
  } finally {
    inflightSubmit.value = false
    stopJudgingIndicator()
  }
}

// Ctrl+Enter runs, Ctrl+Shift+Enter submits - the workbench's primary loop
// should not require leaving the keyboard
function onKeydown(event) {
  if (!(event.ctrlKey || event.metaKey) || event.key !== 'Enter') return
  if (!problem.value || loadError.value) return
  event.preventDefault()
  if (event.shiftKey) submitCode()
  else runCode()
}

onBeforeRouteLeave(() => {
  if (autosaveTimer) {
    flushSave()
  }
  writeSnapshotNow()
  // the code buffer had a flush path here; the notes debounce was only ever
  // cancelled, silently dropping the last keystrokes on every navigation
  if (notesTimer) {
    flushNotesSave()
  }
})

function onBeforeUnload() {
  writeSnapshotNow()
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
    // pending debounced saves must land under the OLD qid: refs still hold
    // the previous problem's content at this point, so flushing with the
    // explicit qid keeps the last keystrokes instead of losing them (a bare
    // cancel used to drop them; letting props.qid be used would corrupt the
    // next problem's files - both halves of the fix are needed together)
    if (autosaveTimer) flushSave(prev)
    clearTimeout(autosaveTimer)
    autosaveTimer = null
    clearTimeout(snapshotTimer)
    snapshotTimer = null
    saveSnapshot(prev, lang.value, code.value)
    if (notesTimer) flushNotesSave(prev)
    clearTimeout(notesTimer)
    notesTimer = null
    verdict.value = null
    loadError.value = ''
    showRestoreBar.value = false
    restoreCandidate.value = null
    statementHtml.value = ''
    notesSavedAt.value = ''
    stopJudgingIndicator()
    loadProblem()
  }
)

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('keydown', onKeydown)
  clearTimeout(autosaveTimer)
  clearTimeout(snapshotTimer)
  clearTimeout(notesTimer)
  stopJudgingIndicator()
})
</script>

<template>
  <section class="page page-wide">
    <div v-if="loading" class="card empty-state">{{ i18n.t('loading_problem') }}</div>

    <template v-else-if="loadError">
      <div class="card empty-state" data-testid="workbench-error">
        <p>{{ loadError }}</p>
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
            <button
              class="fav-btn"
              :class="{ active: favorite }"
              type="button"
              :title="favorite ? i18n.t('fav_remove') : i18n.t('fav_add')"
              data-testid="workbench-fav"
              @click="toggleFavorite"
            >
              {{ favorite ? '★' : '☆' }}
            </button>
            <RouterLink
              v-if="problem.difficulty"
              class="chip chip-link"
              :class="['easy', 'medium', 'hard'].includes(problem.difficulty) ? `chip-${problem.difficulty}` : ''"
              :to="{ path: '/problems', query: { difficulty: problem.difficulty } }"
            >
              {{ difficultyLabel(problem.difficulty) }}
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
            <summary>{{ i18n.t('hints_toggle', { count: (problem.hints || []).length }) }}</summary>
            <ul>
              <li v-for="(hint, index) in problem.hints" :key="index">{{ hint }}</li>
            </ul>
          </details>

          <details class="card notes-card">
            <summary>{{ i18n.t('notes_title') }}</summary>
            <p class="hint-text notes-hint">
              {{ i18n.t('notes_hint') }}
              <span v-if="notesSavedAt" data-testid="notes-saved">· {{ i18n.t('notes_saved') }} {{ notesSavedAt }}</span>
            </p>
            <textarea
              v-model="notesDraft"
              class="input notes-input"
              rows="6"
              data-testid="notes-input"
              :placeholder="i18n.t('notes_placeholder')"
            ></textarea>
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
                  :disabled="judgingBusy"
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
                <span class="kbd">Ctrl ↵</span>
                <button
                  class="btn btn-ghost"
                  type="button"
                  :disabled="judgingBusy"
                  title="Ctrl+Enter"
                  data-testid="run-btn"
                  @click="runCode"
                >
                  {{ i18n.t('run') }}
                </button>
                <span class="kbd">Ctrl+⇧ ↵</span>
                <button
                  class="btn btn-primary"
                  type="button"
                  :disabled="judgingBusy"
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

      <AiChatSidebar
        v-if="problem && problem.supported !== false"
        :qid="problem.slug || props.qid"
        :get-code="() => code"
        :code-lang="lang"
      />
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

.banner-warn {
  border-color: var(--warn);
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

.fav-btn {
  background: transparent;
  border: none;
  color: var(--gray-neutral);
  cursor: pointer;
  font-size: var(--font-size-title);
  line-height: 1;
  padding: 0;
}

.fav-btn:hover,
.fav-btn.active {
  color: var(--warn);
}

.notes-card summary {
  color: var(--gray-neutral);
  cursor: pointer;
  font-size: var(--font-size-caption);
}

.notes-hint {
  margin: var(--space-2) 0;
}

.notes-input {
  resize: vertical;
  width: 100%;
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
