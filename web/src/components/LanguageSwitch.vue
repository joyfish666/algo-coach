<script setup>
import { useI18nStore } from '../stores/i18n'

const i18n = useI18nStore()
</script>

<template>
  <div class="lang-switch" role="group">
    <button
      type="button"
      :class="{ active: i18n.lang === 'zh' }"
      data-testid="lang-zh"
      @click="i18n.set('zh')"
    >
      中
    </button>
    <button
      type="button"
      :class="{ active: i18n.lang === 'en' }"
      data-testid="lang-en"
      @click="i18n.set('en')"
    >
      EN
    </button>
  </div>
</template>

<style scoped>
.lang-switch {
  display: flex;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  overflow: hidden;
  background: var(--bg-primary);
}

button {
  align-items: center;
  background: transparent;
  border: none;
  color: var(--gray-neutral);
  display: flex;
  font-size: var(--font-size-caption);
  height: 32px;
  padding: 0 var(--space-3);
}

button + button {
  border-left: 1px solid var(--border-subtle);
}

button.active {
  background: var(--accent);
  color: #ffffff;
}
</style>
