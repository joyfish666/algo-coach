<script setup>
import { useI18nStore } from '../stores/i18n'
import { useThemeStore } from '../stores/theme'

const theme = useThemeStore()
const i18n = useI18nStore()

const options = [
  { value: 'light', labelKey: 'theme_light', testid: 'light' },
  { value: 'dark', labelKey: 'theme_dark', testid: 'dark' },
  { value: 'system', labelKey: 'theme_system', testid: 'system' },
]
</script>

<template>
  <div class="theme-switch" role="group" :aria-label="i18n.t('settings_appearance')">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      :class="{ active: theme.theme === option.value }"
      :title="i18n.t(option.labelKey)"
      :aria-label="i18n.t(option.labelKey)"
      :data-testid="`theme-${option.testid}`"
      @click="theme.set(option.value)"
    >
      <svg
        v-if="option.value === 'light'"
        viewBox="0 0 24 24"
        width="16"
        height="16"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
      >
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
      <svg
        v-else-if="option.value === 'dark'"
        viewBox="0 0 24 24"
        width="16"
        height="16"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M20.5 13.2A8.5 8.5 0 1 1 10.8 3.5a7 7 0 0 0 9.7 9.7z" />
      </svg>
      <svg
        v-else
        viewBox="0 0 24 24"
        width="16"
        height="16"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <rect x="3" y="4.5" width="18" height="12.5" rx="2" />
        <path d="M9 21h6M12 17.5V21" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.theme-switch {
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
  justify-content: center;
  padding: var(--space-2) var(--space-3);
}

button + button {
  border-left: 1px solid var(--border-subtle);
}

button.active {
  background: var(--accent);
  color: #ffffff;
}
</style>
