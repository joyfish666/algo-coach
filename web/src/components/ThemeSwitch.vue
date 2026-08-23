<script setup>
import { useThemeStore } from '../stores/theme'

const theme = useThemeStore()
const options = [
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '暗色' },
  { value: 'system', label: '跟随系统' },
]
</script>

<template>
  <div class="theme-switch">
    <button
      v-for="option in options"
      :key="option.value"
      :class="{ active: theme.theme === option.value }"
      @click="theme.set(option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>

<style scoped>
.theme-switch {
  display: flex;
  border: 1px solid var(--gray-neutral);
  border-radius: var(--radius-pill);
  overflow: hidden;
}

button {
  border: none;
  background: transparent;
  color: var(--text-primary);
  padding: var(--space-1) var(--space-3);
  font-size: 12px;
}

button.active {
  background: var(--accent);
  color: #ffffff;
}
</style>
