<script setup>
import { computed } from 'vue'

import { useI18nStore } from '../stores/i18n'

const props = defineProps({
  tags: { type: Array, default: () => [] },
})

const i18n = useI18nStore()

const ROW_HEIGHT = 30
const CHART_WIDTH = 640
const LABEL_WIDTH = 150
const PCT_WIDTH = 56
const BAR_X = LABEL_WIDTH + 12
const BAR_WIDTH = CHART_WIDTH - BAR_X - PCT_WIDTH - 8

const height = computed(() => Math.max(props.tags.length, 1) * ROW_HEIGHT + 12)

const bars = computed(() =>
  props.tags.map((tag, index) => {
    const y = index * ROW_HEIGHT + 8
    const fullName = tag.name_zh || tag.name_en || tag.slug || ''
    const pct = Math.round((tag.mastered || 0) * 100)
    return {
      id: `${tag.slug}-${index}`,
      name: fullName.slice(0, 10),
      tip: i18n.t('chart_row_tip', { name: fullName, pct, count: tag.attempted }),
      pct,
      attempted: tag.attempted,
      y,
      fillWidth: Math.max(2, Math.round((BAR_WIDTH * (tag.mastered || 0)))),
      textX: BAR_X + 8,
      pctX: CHART_WIDTH - PCT_WIDTH,
    }
  })
)
</script>

<template>
  <svg
    class="tag-chart"
    :viewBox="`0 0 ${CHART_WIDTH} ${height}`"
    role="img"
    data-testid="tag-chart"
  >
    <g v-for="bar in bars" :key="bar.id">
      <!-- native SVG tooltip: carries the full untruncated tag name plus what
           the trailing number means -->
      <title>{{ bar.tip }}</title>
      <text :x="4" :y="bar.y + 14" class="label">{{ bar.name }}</text>
      <rect
        :x="BAR_X"
        :y="bar.y"
        :width="BAR_WIDTH"
        height="16"
        rx="8"
        class="track"
      />
      <rect
        :x="BAR_X"
        :y="bar.y"
        :width="bar.fillWidth"
        height="16"
        rx="8"
        class="fill"
      />
      <text :x="bar.pctX" :y="bar.y + 14" class="pct">
        {{ bar.pct }}% · {{ bar.attempted }}
      </text>
    </g>
  </svg>
</template>

<style scoped>
.tag-chart {
  width: 100%;
  height: auto;
}

.label {
  fill: var(--text-primary);
  font-size: 13px;
}

.track {
  fill: var(--bg-secondary);
}

.fill {
  fill: var(--accent);
}

.pct {
  fill: var(--gray-neutral);
  font-size: 12px;
  text-anchor: end;
}
</style>
