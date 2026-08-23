<script setup>
import { ref } from 'vue'

import CodeEditor from '../components/CodeEditor.vue'

defineProps({ qid: { type: String, required: true } })

const code = ref('')
const lang = ref('cpp')
const languages = ['cpp', 'python3', 'java']
</script>

<template>
  <section class="page">
    <h1>{{ qid }}</h1>
    <p class="placeholder">答题工作台骨架占位：题面渲染、Run/Submit、结果面板与自定义用例面板将在后续里程碑实现。</p>
    <div class="editor-demo">
      <select v-model="lang">
        <option v-for="item in languages" :key="item" :value="item">{{ item }}</option>
      </select>
      <CodeEditor v-model="code" :lang="lang" />
    </div>
  </section>
</template>

<style scoped>
.editor-demo {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

select {
  width: fit-content;
  padding: var(--space-1) var(--space-2);
}
</style>
