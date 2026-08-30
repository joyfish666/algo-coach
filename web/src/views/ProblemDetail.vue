<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'

import CodeEditor from '../components/CodeEditor.vue'
import AiChatSidebar from '../components/AiChatSidebar.vue'
import NotesPanel from '../components/NotesPanel.vue'
import CasesPanel from '../components/CasesPanel.vue'
import JudgingIndicator from '../components/JudgingIndicator.vue'
import JudgeResultPanel from '../components/JudgeResultPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import ProblemMetaRow from '../components/ProblemMetaRow.vue'
import ProblemStatement from '../components/ProblemStatement.vue'
import { api } from '../api'
import { userFacingError } from '../utils/errors'
import { LANGUAGE_OPTIONS } from '../utils/languages'
import { STORAGE_KEYS, readJsonStorage, writeJsonStorage } from '../utils/storage'
import { useI18nStore } from '../stores/i18n'
import { useToastStore } from '../stores/toast'
import { loadSnapshot, saveSnapshot, snapshotNewerThan } from '../snapshots'

const props = defineProps({ qid: { type: String, required: true } })

const i18n = useI18nStore()
const toast = useToastStore()

const SPLIT_KEY = STORAGE_KEYS.workbenchSplit

const loading = ref(true)
// fatal: the problem itself could not be loaded, the whole workbench cannot
// render. Transient action failures (autosave, run, submit) must NOT land
// here - one flaky PUT used to tear down the entire editor surface.
const loadError = ref('')
const problem = ref(null)
const code = ref('')
const lang = ref('cpp')
const languages = LANGUAGE_OPTIONS
const switchingLang = ref(false)
const useLocalCases = ref(false)

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
// the elapsed-time indicator itself lives in JudgingIndicator; the workbench
// only owns the on/off state
const judgingActive = ref(false)

const favorite = ref(false)
const notesRef = ref(null)

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
// lifted from CasesPanel so the divider drag can open the collapsed panel
const casesOpen = ref(false)

function readSplit() {
  const raw = readJsonStorage(SPLIT_KEY)
  if (raw && typeof raw.mainPct === 'number') {
    // the vertical split is gone: the editor always fills the space above
    // the cases zone, and only an explicit user-dragged cases height is
    // stored now (an old {mainPct, editorPct} shape degrades gracefully)
    return {
      mainPct: raw.mainPct,
      casesHeight: typeof raw.casesHeight === 'number' ? raw.casesHeight : null,
    }
  }
  return { mainPct: 42, casesHeight: null }
}

const split = ref(readSplit())

function persistSplit() {
  writeJsonStorage(SPLIT_KEY, split.value)
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
    // the divider sizes the cases zone; the editor flexes to everything above
    // it. Dragging also opens the collapsed panel so the handle always has
    // visible feedback.
    const minCases = 150
    const maxCases = Math.max(minCases, rect.height - 260)
    split.value.casesHeight = Math.round(
      Math.min(Math.max(minCases, rect.bottom - event.clientY), maxCases)
    )
    casesOpen.value = true
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
    favorite.value = Boolean(data.favorite)

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
  loadError.value = userFacingError(err)
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

// transient failures surface as toasts; the workbench stays alive and the
// user keeps their in-progress code visible
function notifyActionError(err) {
  toast.error({ text: userFacingError(err) })
}

async function runCode() {
  if (judgingBusy.value) return
  inflightRun.value = true
  verdict.value = null
  clearTimeout(autosaveTimer)
  judgingActive.value = true
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
    judgingActive.value = false
  }
}

async function submitCode() {
  if (judgingBusy.value) return
  inflightSubmit.value = true
  verdict.value = null
  clearTimeout(autosaveTimer)
  judgingActive.value = true
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
    judgingActive.value = false
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
  // pending notes flush on their own: ProblemStatement registers its own
  // route-leave guard with the same contract
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
    // next problem's files - both halves of the fix are needed together).
    // NotesPanel flushes its notes debounce through the same contract.
    if (autosaveTimer) flushSave(prev)
    clearTimeout(autosaveTimer)
    autosaveTimer = null
    clearTimeout(snapshotTimer)
    snapshotTimer = null
    saveSnapshot(prev, lang.value, code.value)
    notesRef.value?.flushPendingNotes(prev)
    verdict.value = null
    loadError.value = ''
    showRestoreBar.value = false
    restoreCandidate.value = null
    judgingActive.value = false
    loadProblem()
  }
)

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('keydown', onKeydown)
  clearTimeout(autosaveTimer)
  clearTimeout(snapshotTimer)
  judgingActive.value = false
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
          <ProblemMetaRow
            :problem="problem"
            :favorite="favorite"
            @toggle-favorite="toggleFavorite"
          />
        </template>
      </PageHeader>

      <div class="wb" :class="{ 'wb-dragging': dragActive }" data-testid="workbench">
        <section ref="leftPaneRef" class="pane left-pane" :style="{ width: split.mainPct + '%' }">
          <ProblemStatement
            :markdown="problem.statement_markdown || ''"
            :hints="problem.hints || []"
          />
        </section>

        <div
          class="divider divider-v"
          data-testid="divider-main"
          @mousedown="startDrag('x', $event)"
        ></div>

        <section ref="rightColRef" class="pane right-col">
          <div class="editor-zone">
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

          <div
            class="cases-zone"
            :style="split.casesHeight ? { '--cases-h': split.casesHeight + 'px' } : {}"
          >
            <CasesPanel
              :qid="props.qid"
              :testcases="problem.testcases || ''"
              :open="casesOpen"
              @toggle="casesOpen = $event"
            />
          </div>
        </section>
      </div>

      <JudgingIndicator :active="judgingActive" :submitting="inflightSubmit" />

      <JudgeResultPanel v-if="verdict" :verdict="verdict" @close="verdict = null" />
    </template>

    <!-- outside the loading/error branches on purpose: once a problem has
         loaded, the floating coach panel survives workbench reloads and
         problem switches instead of flickering away with the page content -->
    <AiChatSidebar
      v-if="problem && problem.supported !== false"
      :qid="problem.slug || props.qid"
      :get-code="() => code"
      :code-lang="lang"
    />
    <NotesPanel
      v-if="problem"
      ref="notesRef"
      :qid="problem.slug || props.qid"
      :notes="problem.notes || ''"
    />
  </section>
</template>

<style scoped>
/* the workbench owns exactly one viewport: the page never scrolls; every
   region that can overflow (statement, editor, judge result) scrolls inside
   itself instead */
.page-wide {
  max-width: none;
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
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

.btn-sm {
  padding: var(--space-1) var(--space-4);
}

.wb {
  display: flex;
  flex: 1;
  gap: 0;
  min-height: 0;
  overflow: hidden;
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

.editor-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.editor-zone {
  display: flex;
  flex-direction: column;
  /* the editor is the workbench's primary surface: it always stretches to
     everything above the cases zone instead of splitting by percentage */
  flex: 1;
  min-height: 220px;
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

.cases-zone {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  /* content-sized: a thin bar when collapsed, the full card when expanded,
     so the cases panel is never clipped by the fixed-height workbench. A
     user-dragged height arrives as --cases-h; the cap keeps a stale large
     height from starving the editor on a smaller window. */
  max-height: calc(100% - 260px);
}

/* the judge result appears below the workbench: it shrinks to the space the
   viewport grants and scrolls internally instead of pushing the page taller */
:deep(.result-panel) {
  flex: 0 1 auto;
  margin-top: var(--space-4);
  min-height: 0;
  overflow-y: auto;
}
</style>
