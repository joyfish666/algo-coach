<script setup>
import { useI18nStore } from '../stores/i18n'
import { difficultyClass, difficultyLabel } from '../utils/difficulty'

defineProps({
  problem: { type: Object, required: true },
  favorite: { type: Boolean, default: false },
})

defineEmits(['toggle-favorite'])

const i18n = useI18nStore()
</script>

<template>
  <span class="meta-row">
    <button
      class="fav-btn"
      :class="{ active: favorite }"
      type="button"
      :title="favorite ? i18n.t('fav_remove') : i18n.t('fav_add')"
      data-testid="workbench-fav"
      @click="$emit('toggle-favorite')"
    >
      {{ favorite ? '★' : '☆' }}
    </button>
    <RouterLink
      v-if="problem.difficulty"
      class="chip chip-link"
      :class="difficultyClass(problem.difficulty)"
      :to="{ path: '/problems', query: { difficulty: problem.difficulty } }"
    >
      {{ difficultyLabel(problem.difficulty, problem.difficulty) }}
    </RouterLink>
    <span v-if="problem.paid_only" class="chip">★</span>
    <RouterLink
      v-for="tag in (problem.tags || []).slice(0, 6)"
      :key="tag.slug"
      class="chip chip-link"
      :to="{ path: '/problems', query: { tag: tag.slug } }"
    >
      {{ tag.name_zh || tag.name_en }}
    </RouterLink>
    <code class="slug-code">#{{ problem.slug }}</code>
  </span>
</template>

<style scoped>
.meta-row {
  align-items: center;
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.chip-link:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.slug-code {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
}

.fav-btn {
  background: transparent;
  border: none;
  color: var(--gray-neutral);
  cursor: pointer;
  font-size: var(--font-size-title);
  line-height: 1;
  padding: 0;
}

.fav-btn:hover,
.fav-btn.active {
  color: var(--warn);
}
</style>
