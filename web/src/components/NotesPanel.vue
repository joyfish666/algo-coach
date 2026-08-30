<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'

import { api } from '../api'
import { useI18nStore } from '../stores/i18n'
import { useFloatingPanel } from '../utils/floatingPanel'
import { STORAGE_KEYS } from '../utils/storage'

const props = defineProps({
  qid: { type: String, required: true },
  // freshly loaded problem's notes; adopted whenever the load completes
  notes: { type: String, default: '' },
})

const i18n = useI18nStore()

const { open, pos, panelEl, toggle, startDrag } = useFloatingPanel({
  id: 'notes',
  posKey: STORAGE_KEYS.panelPos,
})

const draft = ref(props.notes)
const savedAt = ref('')
let notesTimer = null

// the notes prop is the freshly loaded problem's content: adopt it when it
// changes (problem switch / reload). Adopting is safe to autosave - the draft
// lands under the same qid it came from.
watch(
  () => props.notes,
  (value) => {
    draft.value = value || ''
  }
)

watch(draft, () => scheduleNotesSave())

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
  savedAt.value = ''
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
    await api.putNotes(qid, draft.value)
    savedAt.value = new Date().toLocaleTimeString()
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
  <button
    class="fab notes-fab"
    :class="{ active: open }"
    type="button"
    :title="i18n.t('notes_title')"
    :aria-label="i18n.t('notes_title')"
    :aria-pressed="open ? 'true' : 'false'"
    data-testid="notes-open"
    @click="toggle"
  >
    <svg
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M11 4H5.5A1.5 1.5 0 0 0 4 5.5v13A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V13" />
      <path d="M17.7 3.6a2 2 0 0 1 2.8 2.8L12.4 14.5l-3.9 1.1 1.1-3.9z" />
    </svg>
  </button>

  <aside
    v-if="open"
    ref="panelEl"
    class="panel card"
    :style="pos ? { left: pos.x + 'px', top: pos.y + 'px', right: 'auto' } : {}"
    data-testid="notes-panel"
  >
    <header class="panel-head" @mousedown="startDrag">
      <h2>{{ i18n.t('notes_title') }}</h2>
      <div class="head-actions">
        <button class="close" type="button" :title="i18n.t('notes_title')" @click="toggle">
          ✕
        </button>
      </div>
    </header>
    <p class="context-hint">
      {{ i18n.t('notes_hint') }}
      <span v-if="savedAt" data-testid="notes-saved">· {{ i18n.t('notes_saved') }} {{ savedAt }}</span>
    </p>
    <textarea
      v-model="draft"
      class="input notes-input"
      :placeholder="i18n.t('notes_placeholder')"
      spellcheck="false"
      data-testid="notes-input"
    ></textarea>
  </aside>
</template>

<style scoped>
/* bottom slot of the button stack; the AI circle sits one slot above (see
   AiChatSidebar) so the two form one vertical group on the right edge */
.notes-fab {
  bottom: var(--space-6);
}

/* identical chrome to the AI button (keep the two blocks in sync): one
   visual language for the workbench's floating panels */
.fab {
  align-items: center;
  background: var(--accent);
  border: none;
  border-radius: 50%;
  box-shadow: var(--shadow-card);
  color: #ffffff;
  cursor: pointer;
  display: flex;
  height: 52px;
  justify-content: center;
  position: fixed;
  right: var(--space-6);
  width: 52px;
  z-index: 39;
}

.fab:hover,
.fab.active {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}

.panel {
  display: flex;
  flex-direction: column;
  /* same clearance as the AI panel: keep the default corner's circular
     buttons visible below the panel */
  height: min(520px, calc(100vh - 176px));
  max-width: 380px;
  position: fixed;
  right: var(--space-6);
  top: var(--space-6);
  width: 340px;
  z-index: 40;
}

.panel-head {
  align-items: center;
  cursor: move;
  display: flex;
  justify-content: space-between;
  user-select: none;
}

.panel-head h2 {
  font-size: var(--font-size-title);
  margin-bottom: 0;
}

.head-actions {
  align-items: center;
  display: flex;
  gap: var(--space-2);
}

.close {
  background: transparent;
  border: none;
  color: var(--gray-neutral);
  cursor: pointer;
  font-size: var(--font-size-title);
}

.context-hint {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  margin: var(--space-1) 0 0;
}

.notes-input {
  flex: 1;
  margin-top: var(--space-3);
  min-height: 0;
  resize: none;
  width: 100%;
}
</style>
