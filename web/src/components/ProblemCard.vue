<script setup>
import { computed } from 'vue'

import { useI18nStore } from '../stores/i18n'

const props = defineProps({
  row: { type: Object, required: true },
})

const i18n = useI18nStore()

const difficultyLabel = computed(() => {
  const map = { easy: 'diff_easy', medium: 'diff_medium', hard: 'diff_hard' }
  const key = map[(props.row.difficulty || '').toLowerCase()]
  return key ? i18n.t(key) : ''
})

const visibleTags = computed(() => (props.row.tags || []).slice(0, 3))
const extraTagCount = computed(() => Math.max(0, (props.row.tags || []).length - 3))

const title = computed(() => props.row.title_cn || props.row.title_en || props.row.slug)
</script>

<template>
  <RouterLink :to="`/problem/${row.slug}`" class="pcard" data-testid="problem-card">
    <span class="pid mono">{{ row.frontend_id }}</span>
    <span class="pmain">
      <span class="ptitle">{{ title }}</span>
      <span v-if="visibleTags.length" class="ptags">
        <span v-for="tag in visibleTags" :key="tag.slug" class="mini-tag">
          {{ tag.name_zh || tag.name_en }}
        </span>
        <span v-if="extraTagCount > 0" class="mini-tag more">+{{ extraTagCount }}</span>
      </span>
    </span>
    <span class="pright">
      <span
        v-if="row.practice_status === 'accepted'"
        class="chip chip-ok"
        data-testid="status-solved"
      >
        ✓ {{ i18n.t('status_solved') }}
      </span>
      <span v-else-if="row.practice_status" class="chip" data-testid="status-attempted">
        {{ i18n.t('status_attempted') }}
      </span>
      <span v-if="difficultyLabel" class="chip">{{ difficultyLabel }}</span>
      <span
        v-if="row.paid_only"
        class="paid-mark"
        :title="i18n.t('premium_tip')"
      >★</span>
      <span v-if="row.supported === false" class="chip chip-unsupported">
        {{ i18n.t('unsupported_short') }}
      </span>
    </span>
  </RouterLink>
</template>

<style scoped>
.pcard {
  align-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  color: var(--text-primary);
  display: flex;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  transition: border-color 0.15s ease;
}

.pcard:hover {
  border-color: var(--accent);
}

.pid {
  color: var(--gray-neutral);
  flex-shrink: 0;
  min-width: 72px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--font-size-caption);
}

.pmain {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.ptitle {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ptags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.mini-tag {
  background: var(--bg-secondary);
  border-radius: var(--space-1);
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  padding: 0 var(--space-2);
}

.more {
  opacity: 0.7;
}

.pright {
  align-items: center;
  display: flex;
  flex-shrink: 0;
  gap: var(--space-2);
  margin-left: auto;
}

.paid-mark {
  color: var(--gray-neutral);
}

.chip-unsupported {
  color: var(--gray-neutral);
}
</style>
