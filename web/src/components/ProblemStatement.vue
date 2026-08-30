<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'

import { api } from '../api'
import { makeMarkdown } from '../utils/markdown'
import { useI18nStore } from '../stores/i18n'

const props = defineProps({
  qid: { type: String, required: true },
  // raw statement markdown; rendered here so the parent keeps no rendering state
  markdown: { type: String, default: '' },
  hints: { type: Array, default: () => [] },
  // freshly loaded problem's notes; adopted whenever the load completes
  notes: { type: String, default: '' },
})

const i18n = useI18nStore()
const md = makeMarkdown()

const statementHtml = computed(() => md.render(props.markdown || ''))

const notesDraft = ref(props.notes)
const notesSavedAt = ref('')
let notesTimer = null

// the notes prop is the freshly loaded problem's content: adopt it when it
// changes (problem switch / reload). Adopting is safe to autosave - the draft
// lands under the same qid it came from.
watch(
  () => props.notes,
  (value) => {
    notesDraft.value = value || ''
  }
)

watch(notesDraft, () => scheduleNotesSave())

// qid changes tear the workbench down into its loading state before this
// component's own qid watcher could fire, so the flush on problem switches
// is parent-driven: the workbench calls flushPendingNotes(oldQid) while refs
// still hold the previous problem's draft. A bare cancel would drop the last
// keystrokes; saving under the new qid would corrupt its notes - the explicit
// old qid keeps both failure modes closed.
function flushPendingNotes(qid) {
  if (notesTimer) flushNotesSave(qid)
  clearTimeout(notesTimer)
  notesTimer = null
  notesSavedAt.value = ''
}

defineExpose({ flushPendingNotes })

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

// the notes debounce was only ever cancelled on navigation, silently dropping
// the last keystrokes - it must flush here like the code buffer does
onBeforeRouteLeave(() => {
  if (notesTimer) {
    flushNotesSave()
  }
})

onBeforeUnmount(() => {
  clearTimeout(notesTimer)
})
</script>

<template>
  <div class="card pane-card">
    <h2>{{ i18n.t('problem_statement') }}</h2>
    <div class="statement" v-html="statementHtml"></div>
  </div>
  <details v-if="hints.length" class="card hints-card">
    <summary>{{ i18n.t('hints_toggle', { count: hints.length }) }}</summary>
    <ul>
      <li v-for="(hint, index) in hints" :key="index">{{ hint }}</li>
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
</template>

<style scoped>
.pane-card {
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

.hint-text {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  margin: var(--space-3) 0;
}
</style>
