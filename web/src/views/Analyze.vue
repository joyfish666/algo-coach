<script setup>
import PageHeader from '../components/PageHeader.vue'
import StatCard from '../components/StatCard.vue'
import { useI18nStore } from '../stores/i18n'

const i18n = useI18nStore()

const stats = [
  { key: 'stat_total' },
  { key: 'stat_easy' },
  { key: 'stat_medium' },
  { key: 'stat_hard' },
]
</script>

<template>
  <section class="page">
    <PageHeader :title="i18n.t('analyze_title')" :subtitle="i18n.t('analyze_subtitle')" />
    <div class="stat-grid">
      <StatCard
        v-for="stat in stats"
        :key="stat.key"
        :label="i18n.t(stat.key)"
        value="--"
      />
    </div>
    <div class="card empty-state chart-card">
      <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
        <path d="M5 20V12M12 20V5.5M19 20v-5" />
      </svg>
      <p>{{ i18n.t('chart_tags') }} · {{ i18n.t('coming_soon') }}</p>
    </div>
  </section>
</template>

<style scoped>
.stat-grid {
  display: grid;
  gap: var(--space-4);
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
}

.chart-card {
  margin-top: var(--space-4);
}
</style>
