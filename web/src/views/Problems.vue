<script setup>
import PageHeader from '../components/PageHeader.vue'
import { useI18nStore } from '../stores/i18n'
import { useStatusStore } from '../stores/status'

const i18n = useI18nStore()
const status = useStatusStore()
</script>

<template>
  <section class="page">
    <PageHeader :title="i18n.t('problems_title')" :subtitle="i18n.t('problems_subtitle')">
      <template #actions>
        <button class="btn btn-primary" type="button" disabled>
          {{ i18n.t('problems_sync') }}
        </button>
      </template>
    </PageHeader>
    <div class="card empty-state" data-testid="problems-empty">
      <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
        <path d="M4 6h16M4 12h16M4 18h10" />
      </svg>
      <p>{{ i18n.t('coming_soon') }}</p>
      <p v-if="status.loaded && !status.reachable" class="offline-hint">
        API: 127.0.0.1:8000
      </p>
    </div>
  </section>
</template>

<style scoped>
.offline-hint {
  font-size: var(--font-size-caption);
  opacity: 0.7;
}
</style>
