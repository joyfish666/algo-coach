<script setup>
import { computed, onMounted, ref } from 'vue'

import PageHeader from '../components/PageHeader.vue'
import StatCard from '../components/StatCard.vue'
import TagMasteryChart from '../components/TagMasteryChart.vue'
import MarkdownIt from 'markdown-it'
import { api } from '../api'
import { useI18nStore } from '../stores/i18n'

const i18n = useI18nStore()
const md = new MarkdownIt({ html: false, linkify: false })

const loading = ref(true)
const errorText = ref('')
const data = ref(null)

const importing = ref(false)
const importMessage = ref('')

const generating = ref(false)
const aiReportHtml = ref('')

const statCards = computed(() => {
  const stats = data.value?.stats
  return [
    { key: 'stat_total', value: String(stats?.solved_total ?? '--') },
    { key: 'stat_easy', value: String(stats?.by_difficulty?.easy ?? '--') },
    { key: 'stat_medium', value: String(stats?.by_difficulty?.medium ?? '--') },
    { key: 'stat_hard', value: String(stats?.by_difficulty?.hard ?? '--') },
  ]
})

async function loadAnalyze(useLlm = false) {
  if (useLlm) generating.value = true
  else loading.value = true
  errorText.value = ''
  try {
    const result = await api.analyze({ use_llm: useLlm })
    data.value = result
    aiReportHtml.value = result.ai_report ? md.render(result.ai_report) : ''
  } catch (err) {
    errorText.value =
      (err.payload && err.payload.error && err.payload.error.message) || err.message || String(err)
  } finally {
    loading.value = false
    generating.value = false
  }
}

async function importSite() {
  if (importing.value) return
  importing.value = true
  importMessage.value = ''
  try {
    const result = await api.importSite(20)
    importMessage.value = i18n.t('analyze_import_done', {
      imported: result.imported,
      skipped: result.skipped,
    })
    await loadAnalyze(false)
  } catch (err) {
    importMessage.value =
      (err.payload && err.payload.error && err.payload.error.message) || err.message || String(err)
  } finally {
    importing.value = false
  }
}

function difficultyLabel(value) {
  const map = { easy: 'diff_easy', medium: 'diff_medium', hard: 'diff_hard' }
  const key = map[(value || '').toLowerCase()]
  return key ? i18n.t(key) : value
}

function difficultyClass(value) {
  const level = (value || '').toLowerCase()
  return ['easy', 'medium', 'hard'].includes(level) ? `chip-${level}` : ''
}

onMounted(() => loadAnalyze(false))
</script>

<template>
  <section class="page">
    <PageHeader :title="i18n.t('analyze_title')" :subtitle="i18n.t('analyze_subtitle')">
      <template #actions>
        <div class="header-actions">
          <button
            class="btn btn-ghost"
            type="button"
            :disabled="importing"
            data-testid="import-btn"
            @click="importSite"
          >
            {{ importing ? i18n.t('analyze_importing') : i18n.t('analyze_import') }}
          </button>
        </div>
      </template>
    </PageHeader>

    <p v-if="importMessage" class="import-note" data-testid="import-note">{{ importMessage }}</p>

    <div v-if="loading" class="card empty-state">{{ i18n.t('analyze_loading') }}</div>

    <div v-else-if="errorText" class="card empty-state">
      <p>{{ errorText }}</p>
      <button class="btn btn-ghost" type="button" @click="loadAnalyze(false)">
        {{ i18n.t('retry') }}
      </button>
    </div>

    <template v-else-if="data">
      <div class="stat-grid">
        <StatCard v-for="item in statCards" :key="item.key" :label="i18n.t(item.key)" :value="item.value" />
      </div>
      <p v-if="data.stats.attempts_total !== undefined" class="attempts-line">
        {{ i18n.t('stat_attempts', { count: data.stats.attempts_total }) }}
      </p>

      <div class="card chart-card">
        <h2>{{ i18n.t('chart_tags') }} · {{ i18n.t('analyze_mastery') }}</h2>
        <TagMasteryChart v-if="(data.tags || []).length" :tags="data.tags.slice(0, 12)" />
        <p v-else class="placeholder">{{ i18n.t('analyze_empty_tags') }}</p>
      </div>

      <div class="two-col">
        <div class="card">
          <h2>{{ i18n.t('recommend_title') }}</h2>
          <ul v-if="(data.recommendations || []).length" class="rec-list">
            <li v-for="row in data.recommendations" :key="row.slug">
              <RouterLink :to="`/problem/${row.slug}`" class="rec-item">
                <span class="mono rec-id">{{ row.frontend_id }}</span>
                <span>{{ row.title_cn || row.title_en || row.slug }}</span>
                <span v-if="row.difficulty" class="chip" :class="difficultyClass(row.difficulty)">{{ difficultyLabel(row.difficulty) }}</span>
              </RouterLink>
            </li>
          </ul>
          <p v-else class="placeholder">{{ i18n.t('recommend_empty') }}</p>
        </div>

        <div class="card">
          <h2>{{ i18n.t('analyze_ai_title') }}</h2>
          <template v-if="data.ai_configured">
            <button
              v-if="!aiReportHtml"
              class="btn btn-primary"
              type="button"
              :disabled="generating"
              data-testid="generate-report"
              @click="loadAnalyze(true)"
            >
              {{ generating ? i18n.t('analyze_ai_generating') : i18n.t('analyze_ai_generate') }}
            </button>
            <div v-else class="report" data-testid="ai-report" v-html="aiReportHtml"></div>
            <p v-if="generating" class="placeholder">{{ i18n.t('analyze_loading') }}</p>
          </template>
          <p v-else class="placeholder">{{ i18n.t('analyze_ai_disabled') }}</p>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.header-actions {
  display: flex;
  justify-content: flex-end;
}

.import-note {
  color: var(--accent);
  font-size: var(--font-size-caption);
  margin: calc(-1 * var(--space-4)) 0 var(--space-4);
}

.stat-grid {
  display: grid;
  gap: var(--space-4);
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
}

.attempts-line {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
}

.chart-card {
  margin-top: var(--space-4);
}

.two-col {
  display: grid;
  gap: var(--space-4);
  grid-template-columns: 1fr 1fr;
  margin-top: var(--space-4);
}

.rec-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
}

.rec-item {
  align-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  color: var(--text-primary);
  display: flex;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
}

.rec-item:hover {
  border-color: var(--accent);
}

.mono,
.rec-id {
  color: var(--gray-neutral);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--font-size-caption);
}

.report :deep(p) {
  margin: var(--space-2) 0;
}

@media (max-width: 960px) {
  .two-col {
    grid-template-columns: 1fr;
  }
}
</style>
