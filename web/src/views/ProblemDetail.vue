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

const loading = ref(true)
const errorText = ref('')
const errorKey = ref('')
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

const useLocalCases = ref(false)
const casesOpen = ref(false)
const casesDraft = ref('')
const casesSaving = ref(false)
const casesSavedAt = ref('')

const inflightRun = ref(false)
const inflightSubmit = ref(false)
const verdict = ref(null)

const restoreCandidate = ref(null)
const showRestoreBar = ref(false)

let autosaveTimer = null

const difficultyLabel = computed(() => {
  const map = { easy: 'Easy', medium: 'Medium', hard: 'Hard' }
  return map[(problem.value?.difficulty || '').toLowerCase()] || ''
})

const renderedStatement = computed(() => statementHtml.value)

function applyError(err) {
  const keyFromServer =
    err && err.payload && err.payload.error && err.payload.error.message_key
  if (keyFromServer) {
    const translated = i18n.t(keyFromServer)
    errorKey.value = translated !== keyFromServer ? keyFromServer : ''
    errorText.value = translated
    return
  }
  if (err && err.status === 403) {
    errorKey.value = 'premium_problem'
    errorText.value = i18n.t('premium_problem')
    return
  }
  errorKey.value = ''
  errorText.value = (err && err.message) || 'error'
}

async function loadProblem() {
  loading.value = true
  errorText.value = ''
  verdict.value = null
  try {
    const data = await api.getProblem(props.qid)
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
    applyError(err)
  } finally {
    loading.value = false
  }
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
    /* keep going; template switch is the priority */
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
  }
}

async function submitCode() {
  if (inflightSubmit.value) return
  inflightSubmit.value = true
  verdict.value = null
  errorText.value = ''
  clearTimeout(autosaveTimer)
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
  }
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
  loadProblem()
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  clearTimeout(autosaveTimer)
})
</script>

<template>
  <section class="page">
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
            <span v-if="difficultyLabel" class="chip">{{ difficultyLabel }}</span>
            <span v-if="problem.paid_only" class="chip">★</span>
            <span v-for="tag in (problem.tags || []).slice(0, 6)" :key="tag.slug" class="chip">
              {{ tag.name_zh || tag.name_en }}
            </span>
            <code class="slug-code">#{{ problem.slug }}</code>
          </span>
        </template>
      </PageHeader>

      <div class="panes">
        <div class="left-col">
          <div class="card statement-card">
            <h2>{{ i18n.t('problem_statement') }}</h2>
            <div class="statement" v-html="renderedStatement"></div>
          </div>

          <details v-if="(problem.hints || []).length" class="card hints-card">
            <summary>{{ (problem.hints || []).length }} × hint</summary>
            <ul>
              <li v-for="(hint, index) in problem.hints" :key="index">{{ hint }}</li>
            </ul>
          </details>
        </div>

        <div class="right-col">
          <div class="card editor-card">
            <div class="editor-head">
              <h2>{{ i18n.t('problem_editor') }}</h2>
              <select
                v-model="lang"
                class="select"
                :disabled="switchingLang"
                data-testid="editor-lang-select"
              >
                <option v-for="item in languages" :key="item.value" :value="item.value">
                  {{ item.label }}
                  <template v-if="!problem.languages_available.includes(item.value)"> ·</template>
                </option>
              </select>
            </div>
            <CodeEditor v-model="code" :lang="lang" />
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
                data-testid="run-btn"
                @click="runCode"
              >
                {{ i18n.t('run') }}
              </button>
              <button
                class="btn btn-primary"
                type="button"
                :disabled="inflightSubmit"
                data-testid="submit-btn"
                @click="submitCode"
              >
                {{ i18n.t('submit') }}
              </button>
            </div>
          </div>

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
      </div>

      <JudgeResultPanel
        v-if="verdict"
        :verdict="verdict"
        :show-input="verdict.mode === 'run'"
      />
    </template>

    <AiChatSidebar v-if="problem && problem.supported !== false" :qid="problem.slug || props.qid" />
  </section>
</template>

<style scoped>
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

.slug-code {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
}

.panes {
  display: grid;
  gap: var(--space-4);
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
}

.left-col,
.right-col {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
}

.statement :deep(p) {
  margin: var(--space-3) 0;
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

.editor-head {
  align-items: center;
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}

.editor-head h2 {
  margin-bottom: 0;
}

.actions-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-top: var(--space-4);
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

@media (max-width: 960px) {
  .panes {
    grid-template-columns: 1fr;
  }
}
</style>
