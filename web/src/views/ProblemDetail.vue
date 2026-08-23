<script setup>
import { ref } from 'vue'

import CodeEditor from '../components/CodeEditor.vue'
import PageHeader from '../components/PageHeader.vue'
import { useI18nStore } from '../stores/i18n'

const props = defineProps({ qid: { type: String, required: true } })

const i18n = useI18nStore()
const code = ref('')
const lang = ref('cpp')
const languages = [
  { value: 'cpp', label: 'C++' },
  { value: 'python3', label: 'Python 3' },
  { value: 'java', label: 'Java' },
]
</script>

<template>
  <section class="page">
    <PageHeader :title="props.qid" :subtitle="i18n.t('coming_soon')" />
    <div class="panes">
      <div class="card pane-statement">
        <h2>{{ i18n.t('problem_statement') }}</h2>
        <p class="placeholder">{{ i18n.t('coming_soon') }}</p>
      </div>
      <div class="card pane-editor">
        <div class="editor-head">
          <h2>{{ i18n.t('problem_editor') }}</h2>
          <select v-model="lang" class="select" data-testid="editor-lang-select">
            <option v-for="item in languages" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </div>
        <CodeEditor v-model="code" :lang="lang" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.panes {
  display: grid;
  gap: var(--space-4);
  grid-template-columns: 1fr 1fr;
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

@media (max-width: 960px) {
  .panes {
    grid-template-columns: 1fr;
  }
}
</style>
