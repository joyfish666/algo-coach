<script setup>
import { computed } from 'vue'

import { useI18nStore } from '../stores/i18n'

const props = defineProps({
  verdict: { type: Object, required: true },
  showInput: { type: Boolean, default: false },
})

const i18n = useI18nStore()

const statusKey = computed(() => props.verdict.status_key || 'unknown')

const statusText = computed(() => {
  const key = `verdict_${statusKey.value}`
  const translated = i18n.t(key)
  if (translated !== key) return translated
  return props.verdict.status_msg || '—'
})

const hasMetrics = computed(
  () => Boolean(props.verdict.runtime_display || props.verdict.memory_display)
)

const caseCounts = computed(() => {
  const correct = props.verdict.total_correct
  const total = props.verdict.total_testcases
  if (correct === null || correct === undefined || total === null || total === undefined) {
    return ''
  }
  return `${correct} / ${total}`
})

const waRows = computed(() => {
  if (statusKey.value !== 'wrong_answer') return []
  const expected = props.verdict.expected_outputs || []
  const actual = props.verdict.outputs || []
  const rows = []
  const len = Math.max(expected.length, actual.length)
  for (let i = 0; i < len; i += 1) {
    rows.push({ expected: expected[i] ?? '—', actual: actual[i] ?? '—' })
  }
  return rows
})

const compileError = computed(() => (statusKey.value === 'compile_error'
  ? props.verdict.compile_error || props.verdict.status_msg
  : ''))

const runtimeError = computed(() => (statusKey.value === 'runtime_error'
  ? props.verdict.runtime_error || ''
  : ''))
</script>

<template>
  <div class="card result-panel" data-testid="judge-result">
    <div class="headline" :class="`is-${statusKey}`">{{ statusText }}</div>

    <p v-if="statusKey === 'unknown'" class="unknown-hint">
      {{ i18n.t('verdict_unknown_hint') }}
      <code v-if="verdict.submission_id">#{{ verdict.submission_id }}</code>
    </p>

    <div v-if="hasMetrics" class="metrics">
      <div v-if="verdict.runtime_display" class="metric">
        <span class="metric-label">{{ i18n.t('label_runtime') }}</span>
        <span class="metric-value">
          {{ verdict.runtime_display }}
          <em v-if="verdict.runtime_percentile !== null && verdict.runtime_percentile !== undefined">
            {{ i18n.t('label_beat') }} {{ verdict.runtime_percentile }}%
          </em>
        </span>
      </div>
      <div v-if="verdict.memory_display" class="metric">
        <span class="metric-label">{{ i18n.t('label_memory') }}</span>
        <span class="metric-value">
          {{ verdict.memory_display }}
          <em v-if="verdict.memory_percentile !== null && verdict.memory_percentile !== undefined">
            {{ i18n.t('label_beat') }} {{ verdict.memory_percentile }}%
          </em>
        </span>
      </div>
      <div v-if="caseCounts" class="metric">
        <span class="metric-label">{{ i18n.t('label_cases_passed') }}</span>
        <span class="metric-value">{{ caseCounts }}</span>
      </div>
    </div>

    <table v-if="waRows.length" class="wa-table">
      <thead>
        <tr>
          <th v-if="showInput">{{ i18n.t('label_input') }}</th>
          <th>{{ i18n.t('label_expected') }}</th>
          <th>{{ i18n.t('label_actual') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in waRows" :key="index">
          <td v-if="showInput" class="mono">—</td>
          <td class="mono">{{ row.expected }}</td>
          <td class="mono diff">{{ row.actual }}</td>
        </tr>
      </tbody>
    </table>

    <details v-if="compileError" open class="error-block">
      <summary>{{ i18n.t('label_compile_error') }}</summary>
      <pre class="mono">{{ compileError }}</pre>
    </details>

    <details v-if="runtimeError" class="error-block">
      <summary>{{ i18n.t('label_runtime_error') }}</summary>
      <pre class="mono">{{ runtimeError }}</pre>
    </details>

    <details v-if="verdict.stdout_tail" class="error-block">
      <summary>{{ i18n.t('label_stdout') }}</summary>
      <pre class="mono">{{ verdict.stdout_tail }}</pre>
    </details>
  </div>
</template>

<style scoped>
.headline {
  font-size: var(--font-size-page);
  font-weight: 700;
  line-height: 1.2;
}

.is-accepted {
  color: var(--accent);
}

.is-unknown {
  color: var(--gray-neutral);
}

.unknown-hint {
  color: var(--gray-neutral);
  margin: var(--space-2) 0 0;
}

.metrics {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  margin-top: var(--space-4);
}

.metric-label {
  color: var(--gray-neutral);
  display: block;
  font-size: var(--font-size-caption);
}

.metric-value {
  font-size: var(--font-size-title);
  font-weight: 700;
}

.metric-value em {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  font-style: normal;
  margin-left: var(--space-1);
}

.wa-table {
  border-collapse: collapse;
  margin-top: var(--space-4);
  width: 100%;
}

.wa-table th,
.wa-table td {
  border: 1px solid var(--border-subtle);
  padding: var(--space-2) var(--space-3);
  text-align: left;
  word-break: break-all;
}

.wa-table th {
  background: var(--bg-secondary);
  font-weight: 600;
}

.diff {
  color: var(--accent);
}

.error-block {
  margin-top: var(--space-4);
}

.error-block summary {
  color: var(--gray-neutral);
  cursor: pointer;
  font-size: var(--font-size-caption);
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--font-size-caption);
}
</style>
