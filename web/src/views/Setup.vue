<script setup>
import PageHeader from '../components/PageHeader.vue'
import { useI18nStore } from '../stores/i18n'

const i18n = useI18nStore()
</script>

<template>
  <section class="page setup-page">
    <div class="card setup-card">
      <svg
        class="setup-icon"
        viewBox="0 0 24 24"
        width="40"
        height="40"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
      >
        <path d="M8.5 7 4 12l4.5 5" />
        <path d="m15.5 7 4.5 5-4.5 5" />
        <path d="m13.2 5.5-2.4 13" />
      </svg>
      <h1>{{ i18n.t('setup_title') }}</h1>
      <p class="page-subtitle">{{ i18n.t('setup_subtitle') }}</p>
      <p class="body">{{ i18n.t('setup_body') }}</p>
      <RouterLink class="btn btn-ghost" to="/problems">
        {{ i18n.t('goto_problems') }}
      </RouterLink>
    </div>
  </section>
</template>

<style scoped>
.setup-page {
  align-items: center;
  display: flex;
  min-height: calc(100vh - var(--space-8) * 2);
}

.setup-card {
  margin: 0 auto;
  max-width: 520px;
  text-align: center;
}

.setup-card h1 {
  font-size: var(--font-size-page);
  font-weight: 700;
  margin: var(--space-4) 0 var(--space-1);
}

.setup-icon {
  color: var(--accent);
}

.body {
  color: var(--gray-neutral);
  margin: var(--space-4) 0 var(--space-6);
}
</style>
