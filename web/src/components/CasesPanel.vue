<script setup>
import { ref, watch } from 'vue'

import { api } from '../api'
import { userFacingError } from '../utils/errors'
import { useI18nStore } from '../stores/i18n'
import { useToastStore } from '../stores/toast'

const props = defineProps({
  qid: { type: String, required: true },
  // the freshly loaded problem's stored testcases.txt content
  testcases: { type: String, default: '' },
// lifted to the workbench so the divider drag can open the collapsed panel
open: { type: Boolean, default: false },
})

defineEmits(['toggle'])

const i18n = useI18nStore()
const toast = useToastStore()

// explicit save only (no debounce): unlike code/notes there is no flush
// contract on problem switches - an unsaved draft is simply discarded,
// exactly like the pre-split behavior
const draft = ref(props.testcases)
const saving = ref(false)
const savedAt = ref('')

watch(
  () => props.testcases,
  (value) => {
    draft.value = value || ''
  }
)

// transient failures surface as toasts; the panel keeps the user's draft
async function save() {
  if (saving.value) return
  saving.value = true
  try {
    await api.putTestcases(props.qid, draft.value)
    savedAt.value = new Date().toLocaleTimeString()
  } catch (err) {
    toast.error({ text: userFacingError(err) })
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <details class="card cases-card" :open="open" @toggle="$emit('toggle', $event.target.open)">
    <summary>{{ i18n.t('custom_cases') }}</summary>
    <p class="hint-text">{{ i18n.t('custom_cases_hint') }}</p>
    <textarea
      v-model="draft"
      class="input cases-input mono"
      rows="5"
      spellcheck="false"
      data-testid="cases-input"
    ></textarea>
    <div class="actions-row">
      <button
        class="btn btn-primary"
        type="button"
        :disabled="saving"
        data-testid="cases-save"
        @click="save"
      >
        {{ i18n.t('save_cases') }}
      </button>
      <span v-if="savedAt" class="saved-hint" data-testid="cases-saved">{{ i18n.t('cases_saved') }} · {{ savedAt }}</span>
    </div>
  </details>
</template>

<style scoped>
.cases-card {
  display: flex;
  flex-direction: column;
  max-height: 100%;
  min-height: 0;
  overflow-y: auto;
}

/* without a divider-dragged height (--cases-h from the workbench) the open
   card is content-sized, so the textarea and save row always show fully */
.cases-card[open] {
  height: var(--cases-h, auto);
}

.cases-card summary {
  color: var(--gray-neutral);
  cursor: pointer;
  flex-shrink: 0;
}

.hint-text {
  color: var(--gray-neutral);
  flex-shrink: 0;
  font-size: var(--font-size-caption);
  margin: var(--space-3) 0;
}

.cases-input {
  flex: 1;
  min-height: 96px;
  width: 100%;
}

.saved-hint {
  color: var(--accent);
  font-size: var(--font-size-caption);
}

.actions-row {
  align-items: center;
  display: flex;
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-top: var(--space-3);
}
</style>
