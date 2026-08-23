<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import PageHeader from '../components/PageHeader.vue'
import { api } from '../api'
import { useI18nStore } from '../stores/i18n'

const i18n = useI18nStore()
const router = useRouter()

const loading = ref(true)
const errorText = ref('')
const daily = ref(null)

const difficultyLabel = (value) => {
  const map = { easy: 'diff_easy', medium: 'diff_medium', hard: 'diff_hard' }
  const key = map[(value || '').toLowerCase()]
  return key ? i18n.t(key) : ''
}

async function loadDaily() {
  loading.value = true
  errorText.value = ''
  daily.value = null
  try {
    daily.value = await api.getDaily()
  } catch (err) {
    errorText.value =
      (err.payload && err.payload.error && err.payload.error.message) || err.message || String(err)
  } finally {
    loading.value = false
  }
}

onMounted(loadDaily)
</script>

<template>
  <section class="page">
    <PageHeader :title="i18n.t('daily_title')" :subtitle="i18n.t('daily_subtitle')" />

    <div v-if="loading" class="card empty-state">{{ i18n.t('daily_loading') }}</div>

    <div v-else-if="errorText" class="card empty-state">
      <p>{{ errorText }}</p>
      <button class="btn btn-ghost" type="button" @click="loadDaily">
        {{ i18n.t('retry') }}
      </button>
    </div>

    <div v-else-if="!daily" class="card empty-state" data-testid="daily-empty">
      <p>{{ i18n.t('daily_empty') }}</p>
      <button class="btn btn-ghost" type="button" @click="loadDaily">
        {{ i18n.t('retry') }}
      </button>
    </div>

    <div v-else class="card daily-card" data-testid="daily-card">
      <div class="date-line">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" />
          <path d="M3.5 9.5h17M8 3v3.5M16 3v3.5" />
        </svg>
        <span>{{ daily.date || '' }}</span>
        <span v-if="difficultyLabel(daily.difficulty)" class="chip">
          {{ difficultyLabel(daily.difficulty) }}
        </span>
        <span v-if="daily.paid_only" class="chip">★</span>
      </div>
      <h2 class="daily-title">
        <span class="mono pid">{{ daily.frontend_id }}</span>
        {{ daily.title_cn || daily.title_en || daily.slug }}
      </h2>
      <div v-if="(daily.tags || []).length" class="tag-row">
        <span v-for="tag in daily.tags.slice(0, 6)" :key="tag.slug" class="chip">
          {{ tag.name_zh || tag.name_en }}
        </span>
      </div>
      <button
        class="btn btn-primary"
        type="button"
        data-testid="open-workbench"
        @click="router.push(`/problem/${daily.slug}`)"
      >
        {{ i18n.t('open_workbench') }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.daily-card {
  margin: 0 auto;
  max-width: 640px;
  text-align: center;
}

.date-line {
  align-items: center;
  color: var(--gray-neutral);
  display: flex;
  font-size: var(--font-size-caption);
  gap: var(--space-2);
  justify-content: center;
}

.daily-title {
  font-size: var(--font-size-page);
  font-weight: 700;
  margin: var(--space-4) 0;
}

.pid {
  color: var(--gray-neutral);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  margin-right: var(--space-2);
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  justify-content: center;
  margin-bottom: var(--space-6);
}
</style>
