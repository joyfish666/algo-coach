<script setup>
import PageHeader from '../components/PageHeader.vue'
import { useI18nStore } from '../stores/i18n'

const i18n = useI18nStore()
</script>

<template>
  <section class="page">
    <PageHeader :title="i18n.t('daily_title')" :subtitle="i18n.t('daily_subtitle')" />
    <div class="card empty-state">
      <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" />
        <path d="M3.5 9.5h17M8 3v3.5M16 3v3.5" />
      </svg>
      <p>{{ i18n.t('coming_soon') }}</p>
    </div>
  </section>
</template>
