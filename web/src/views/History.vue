<script setup>
import { onMounted, ref } from 'vue'

import PageHeader from '../components/PageHeader.vue'
import { api } from '../api'
import { useI18nStore } from '../stores/i18n'
import { verdictLabel, verdictTone } from '../utils/verdict'

const i18n = useI18nStore()

const loading = ref(true)
const errorText = ref('')
const records = ref([])
const qidFilter = ref('')
const limit = ref(100)

// verdict -> localized label + semantic color class; one shared mapping with
// JudgeResultPanel so a new status_key falls back to neutral instead of
// silently miscoloring (or showing a raw English enum in the zh UI)
function statusClass(statusKey) {
  const tone = verdictTone(statusKey)
  if (tone === 'accepted') return 'chip-ok'
  if (tone === 'failed') return 'chip-bad'
  return ''
}

function statusLabel(statusKey) {
  return verdictLabel(i18n, statusKey, statusKey)
}

function detailRows(record) {
  const expected = record.expected_outputs || []
  const actual = record.outputs || []
  const len = Math.max(expected.length, actual.length)
  const rows = []
  for (let i = 0; i < len; i += 1) {
    rows.push({ expected: expected[i] ?? '—', actual: actual[i] ?? '—' })
  }
  return rows
}

async function loadHistory() {
  loading.value = true
  errorText.value = ''
  try {
    const data = await api.archiveRecent({
      limit: limit.value,
      qid: qidFilter.value.trim() || undefined,
    })
    records.value = data.records || []
  } catch (err) {
    errorText.value = err.message || String(err)
  } finally {
    loading.value = false
  }
}

onMounted(loadHistory)
</script>

<template>
  <section class="page">
    <PageHeader :title="i18n.t('history_title')" :subtitle="i18n.t('history_subtitle')">
      <template #actions>
        <div class="toolbar">
          <input
            v-model="qidFilter"
            class="input"
            type="search"
            :placeholder="i18n.t('history_filter_placeholder')"
            data-testid="history-qid-input"
            @keydown.enter="loadHistory"
          />
          <select v-model.number="limit" class="select" data-testid="history-limit">
            <option :value="50">50</option>
            <option :value="100">100</option>
            <option :value="200">200</option>
          </select>
          <button class="btn btn-primary" type="button" data-testid="history-apply" @click="loadHistory">
            {{ i18n.t('history_apply') }}
          </button>
        </div>
      </template>
    </PageHeader>

    <div v-if="loading" class="card empty-state">{{ i18n.t('history_loading') }}</div>

    <div v-else-if="errorText" class="card empty-state">
      <p>{{ errorText }}</p>
      <button class="btn btn-ghost" type="button" @click="loadHistory">{{ i18n.t('retry') }}</button>
    </div>

    <div v-else-if="!records.length" class="card empty-state" data-testid="history-empty">
      <!-- one message claimed "no submissions at all" when a filter merely
           matched nothing, making users doubt the filter had applied -->
      <p>{{ qidFilter.trim() ? i18n.t('history_no_match') : i18n.t('history_empty') }}</p>
    </div>

    <div v-else class="card" data-testid="history-table-card">
      <p class="count-line">{{ i18n.t('history_rows', { count: records.length }) }}</p>
      <table class="history-table" data-testid="history-table">
        <thead>
          <tr>
            <th>{{ i18n.t('col_time') }}</th>
            <th>{{ i18n.t('col_problem') }}</th>
            <th>{{ i18n.t('col_lang') }}</th>
            <th>{{ i18n.t('col_verdict') }}</th>
            <th>{{ i18n.t('label_runtime') }}</th>
            <th>{{ i18n.t('label_memory') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(record, index) in records" :key="`${record.submission_id}-${index}`">
            <tr>
              <td class="mono">{{ i18n.formatDateTime(record.timestamp) }}</td>
              <td>
                <RouterLink :to="`/problem/${record.slug}`" class="problem-link">
                  <span class="mono fid">{{ record.frontend_id }}</span>
                  {{ record.slug }}
                </RouterLink>
              </td>
              <td class="mono">{{ record.lang }}</td>
              <td>
                <details class="detail" v-if="detailRows(record).length || record.compile_error || record.runtime_error">
                  <summary><span class="chip" :class="statusClass(record.status)">{{ statusLabel(record.status) }}</span></summary>
                  <div class="detail-body">
                    <table v-if="detailRows(record).length" class="wa-table">
                      <thead>
                        <tr>
                          <th>{{ i18n.t('label_expected') }}</th>
                          <th>{{ i18n.t('label_actual') }}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(row, rowIndex) in detailRows(record)" :key="rowIndex">
                          <td class="mono">{{ row.expected }}</td>
                          <td class="mono">{{ row.actual }}</td>
                        </tr>
                      </tbody>
                    </table>
                    <pre v-if="record.compile_error" class="mono err">{{ record.compile_error }}</pre>
                    <pre v-if="record.runtime_error" class="mono err">{{ record.runtime_error }}</pre>
                  </div>
                </details>
                <span v-else class="chip" :class="statusClass(record.status)">{{ statusLabel(record.status) }}</span>
              </td>
              <td class="mono">{{ record.runtime_display || '—' }}</td>
              <td class="mono">{{ record.memory_display || '—' }}</td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.count-line {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  margin: 0 0 var(--space-2);
}

.history-table {
  border-collapse: collapse;
  width: 100%;
}

.history-table th,
.history-table td {
  border-bottom: 1px solid var(--border-subtle);
  font-size: var(--font-size-caption);
  padding: var(--space-2) var(--space-3);
  text-align: left;
  white-space: nowrap;
}

.history-table th {
  color: var(--gray-neutral);
  font-weight: 600;
}

.problem-link {
  color: var(--text-primary);
}

.problem-link:hover {
  color: var(--accent);
}

.fid {
  color: var(--gray-neutral);
  margin-right: var(--space-1);
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.chip-bad {
  border-color: var(--danger);
  color: var(--danger);
}

.detail summary {
  cursor: pointer;
  list-style: none;
}

.detail-body {
  padding-top: var(--space-2);
  white-space: normal;
}

.wa-table {
  border-collapse: collapse;
}

.wa-table th,
.wa-table td {
  border: 1px solid var(--border-subtle);
  padding: 2px var(--space-2);
}

.err {
  margin: var(--space-2) 0 0;
  white-space: pre-wrap;
}
</style>
