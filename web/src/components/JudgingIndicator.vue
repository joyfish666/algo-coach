<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'

import { useI18nStore } from '../stores/i18n'

const props = defineProps({
  // driven by the workbench's judging gate: true while run/submit is in flight
  active: { type: Boolean, default: false },
  // formal submissions take up to ~2 minutes; say so instead of leaving the
  // user guessing whether the wait is normal
  submitting: { type: Boolean, default: false },
})

const i18n = useI18nStore()

const seconds = ref(0)
let timer = null

watch(
  () => props.active,
  (on) => {
    clearInterval(timer)
    timer = null
    if (on) {
      seconds.value = 0
      timer = setInterval(() => (seconds.value += 1), 1000)
    }
  }
)

onBeforeUnmount(() => {
  clearInterval(timer)
})
</script>

<template>
  <div v-if="active" class="card judging-card" data-testid="judging-indicator">
    <span class="judging-dot"></span>
    <span>{{ i18n.t('judging_in_progress') }}</span>
    <span class="judging-seconds">{{ seconds }}s</span>
    <span v-if="submitting" class="hint-text">{{ i18n.t('judging_submit_hint') }}</span>
  </div>
</template>

<style scoped>
.judging-card {
  align-items: center;
  color: var(--text-primary);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-4);
}

.judging-dot {
  animation: judging-pulse 1s infinite;
  background: var(--accent);
  border-radius: 50%;
  display: inline-block;
  height: 8px;
  width: 8px;
}

.judging-seconds {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  min-width: 3ch;
}

.hint-text {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
}

@keyframes judging-pulse {
  50% {
    opacity: 0.3;
  }
}
</style>
