<script setup>
import { computed } from 'vue'

import { makeMarkdown } from '../utils/markdown'
import { useI18nStore } from '../stores/i18n'

const props = defineProps({
  // raw statement markdown; rendered here so the parent keeps no rendering state
  markdown: { type: String, default: '' },
  hints: { type: Array, default: () => [] },
})

const i18n = useI18nStore()
const md = makeMarkdown()

const statementHtml = computed(() => md.render(props.markdown || ''))
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
</template>

<style scoped>
.pane-card {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.statement {
  flex: 1;
  min-height: 0;
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

/* markdown pipe tables arrive with no borders at all (browser default) - the
   grid lines are what makes an 整数/二进制 table readable */
.statement :deep(table) {
  border-collapse: collapse;
  margin: var(--space-3) 0;
}

.statement :deep(th),
.statement :deep(td) {
  border: 1px solid var(--border-subtle);
  padding: var(--space-1) var(--space-3);
  text-align: left;
  word-break: break-word;
}

.statement :deep(th) {
  background: var(--bg-secondary);
  font-weight: 600;
}

.hints-card {
  flex-shrink: 0;
}

.hints-card summary {
  color: var(--gray-neutral);
  cursor: pointer;
}

.hints-card ul {
  margin: var(--space-3) 0 0;
  padding-left: var(--space-6);
}
</style>
