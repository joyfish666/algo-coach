<script setup>
import { useI18nStore } from '../stores/i18n'
import { useToastStore } from '../stores/toast'

const i18n = useI18nStore()
const toast = useToastStore()
</script>

<template>
  <Teleport to="body">
    <div class="toast-host" data-testid="toast-host">
      <TransitionGroup name="toast">
        <div
          v-for="item in toast.items"
          :key="item.id"
          class="toast"
          :class="`is-${item.kind}`"
          :data-testid="`toast-${item.kind}`"
          role="status"
        >
          <span class="toast-text">{{ item.text }}</span>
          <button
            class="toast-close"
            type="button"
            :title="i18n.t('dismiss')"
            @click="toast.dismiss(item.id)"
          >
            ✕
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-host {
  align-items: flex-end;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  pointer-events: none;
  position: fixed;
  right: var(--space-6);
  top: var(--space-6);
  z-index: 70;
}

.toast {
  align-items: center;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-left: 3px solid var(--gray-neutral);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  color: var(--text-primary);
  display: flex;
  gap: var(--space-3);
  max-width: 380px;
  padding: var(--space-3) var(--space-4);
  pointer-events: auto;
}

.toast.is-success {
  border-left-color: var(--ok);
}

.toast.is-error {
  border-left-color: var(--danger);
}

.toast.is-info {
  border-left-color: var(--accent);
}

.toast-text {
  font-size: var(--font-size-body);
  word-break: break-word;
}

.toast-close {
  background: transparent;
  border: none;
  color: var(--gray-neutral);
  flex-shrink: 0;
  font-size: var(--font-size-caption);
}

.toast-enter-active,
.toast-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
