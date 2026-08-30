<script setup>
import { computed, onMounted } from 'vue'

import GroupPickerPopover from './GroupPickerPopover.vue'
import StarIcon from './StarIcon.vue'
import { useGroupsStore } from '../stores/groups'
import { useI18nStore } from '../stores/i18n'
import { difficultyClass, difficultyLabel } from '../utils/difficulty'

const props = defineProps({
  problem: { type: Object, required: true },
  favorite: { type: Boolean, default: false },
})

defineEmits(['toggle-favorite'])

const i18n = useI18nStore()
const groups = useGroupsStore()

// chips for the groups this problem belongs to; the shared tree snapshot
// loads lazily and a failure here must not touch the workbench itself
onMounted(() => {
  groups.ensure().catch(() => {})
})

const memberGroups = computed(() => groups.groupsOfSlug(props.problem.slug || ''))
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
      <StarIcon :filled="favorite" />
    </button>
    <GroupPickerPopover v-if="problem.slug" :slug="problem.slug" align="left" class="meta-grp" />
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
    <RouterLink
      v-for="group in memberGroups"
      :key="group.id"
      class="chip chip-link group-chip"
      :to="{ path: '/groups', query: { group: group.id } }"
      :data-testid="`meta-group-${group.id}`"
    >
      {{ group.name }}
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

.group-chip {
  background: var(--bg-secondary);
}

.slug-code {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
}

.fav-btn {
  align-items: center;
  background: transparent;
  border: none;
  color: var(--gray-neutral);
  cursor: pointer;
  display: inline-flex;
  font-size: var(--font-size-title);
  line-height: 1;
  padding: 0;
}

.fav-btn:hover,
.fav-btn.active {
  color: var(--warn);
}
</style>
