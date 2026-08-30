<script setup>
import { computed, nextTick, ref } from 'vue'

import { useGroupsStore } from '../stores/groups'
import { useI18nStore } from '../stores/i18n'
import { useToastStore } from '../stores/toast'

// Shared "add to group" picker used by the list rows and the workbench meta
// row. The group list renders FLAT with full path labels ("2026 / 0830")
// instead of a tree dropdown: with unbounded nesting a tree popover becomes
// unscrollable, while paths stay readable at any depth. Membership toggles
// in place (check mark = member), mirroring the favorite star's two-state
// semantics; feedback is the check mark itself, no toast.
const props = defineProps({
  slug: { type: String, required: true },
  // which edge of the trigger the panel anchors to: list rows sit at the
  // viewport's right edge (right), the workbench meta row starts left
  align: { type: String, default: 'right' },
})

const store = useGroupsStore()
const i18n = useI18nStore()
const toast = useToastStore()

const open = ref(false)
const busy = ref(false)
const query = ref('')
const newName = ref('')
const searchInput = ref(null)

const memberSet = computed(
  () => new Set(store.groupsOfSlug(props.slug).map((group) => group.id))
)

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return store.groups
  return store.groups.filter((group) =>
    `${store.pathOf(group.id)} ${group.slugs.join(' ')}`.toLowerCase().includes(needle)
  )
})

async function toggle() {
  if (open.value) {
    open.value = false
    return
  }
  if (!props.slug || busy.value) return
  open.value = true
  try {
    await store.ensure()
  } catch (err) {
    toast.error({ text: err.message || String(err) })
    open.value = false
    return
  }
  await nextTick()
  searchInput.value?.focus()
}

function close() {
  open.value = false
  query.value = ''
}

async function toggleMembership(group) {
  if (busy.value) return
  busy.value = true
  try {
    if (memberSet.value.has(group.id)) {
      await store.removeSlug(group.id, props.slug)
    } else {
      await store.addSlugs(group.id, [props.slug])
    }
  } catch (err) {
    toast.error({ text: err.message || String(err) })
  } finally {
    busy.value = false
  }
}

async function createAndAdd() {
  const name = newName.value.trim()
  if (!name || busy.value) return
  busy.value = true
  try {
    const created = await store.create(name, null)
    newName.value = ''
    if (created) await store.addSlugs(created.id, [props.slug])
  } catch (err) {
    toast.error({ text: err.message || String(err) })
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <span class="grp-wrap">
    <button
      class="grp-btn"
      type="button"
      :title="i18n.t('groups_pick_group')"
      :aria-expanded="open ? 'true' : 'false'"
      data-testid="group-toggle"
      @click.stop.prevent="toggle"
    >
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M3.5 7.5a2 2 0 0 1 2-2h3.6l2 2h7.4a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" />
        <path d="M12 10.5v5M9.5 13h5" />
      </svg>
    </button>
    <span v-if="open" class="grp-backdrop" @click="close"></span>
    <span v-if="open" class="grp-pop" :class="align" @keydown.esc="close">
      <p class="grp-title">{{ i18n.t('groups_pick_group') }}</p>
      <input
        ref="searchInput"
        v-model="query"
        class="input grp-search"
        type="search"
        :placeholder="i18n.t('problems_search_placeholder')"
        data-testid="group-search"
      />
      <div class="grp-list">
        <button
          v-for="group in filtered"
          :key="group.id"
          type="button"
          class="grp-row"
          :class="{ member: memberSet.has(group.id) }"
          :data-testid="`group-option-${group.id}`"
          @click.stop="toggleMembership(group)"
        >
          <span class="grp-check">{{ memberSet.has(group.id) ? '✓' : '' }}</span>
          <span class="grp-path">{{ store.pathOf(group.id) }}</span>
        </button>
        <p v-if="!store.groups.length" class="grp-empty" data-testid="group-picker-empty">
          {{ i18n.t('groups_no_group_yet') }}
        </p>
        <p v-else-if="!filtered.length" class="grp-empty">{{ i18n.t('no_match') }}</p>
      </div>
      <div class="grp-new">
        <input
          v-model="newName"
          class="input"
          type="text"
          :placeholder="i18n.t('groups_new_group_placeholder')"
          data-testid="group-new-name"
          @keydown.enter.stop.prevent="createAndAdd"
        />
        <button
          class="btn btn-ghost btn-sm"
          type="button"
          :disabled="!newName.trim() || busy"
          data-testid="group-create-add"
          @click.stop="createAndAdd"
        >
          {{ i18n.t('groups_create_add') }}
        </button>
      </div>
    </span>
  </span>
</template>

<style scoped>
.grp-wrap {
  display: inline-flex;
  position: relative;
}

.grp-btn {
  align-items: center;
  background: transparent;
  border: none;
  color: var(--gray-neutral);
  cursor: pointer;
  display: inline-flex;
  line-height: 1;
  padding: 0;
}

.grp-btn:hover {
  color: var(--accent);
}

.grp-backdrop {
  inset: 0;
  position: fixed;
  z-index: 40;
}

.grp-pop {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  position: absolute;
  top: calc(100% + 6px);
  width: 280px;
  z-index: 41;
}

.grp-pop.right {
  right: 0;
}

.grp-pop.left {
  left: 0;
}

.grp-title {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  margin: 0;
}

.grp-list {
  display: flex;
  flex-direction: column;
  max-height: 260px;
  overflow-y: auto;
}

.grp-row {
  align-items: center;
  background: transparent;
  border: none;
  border-radius: var(--space-1);
  cursor: pointer;
  display: flex;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  text-align: left;
}

.grp-row:hover {
  background: var(--bg-secondary);
}

.grp-check {
  color: var(--accent);
  flex-shrink: 0;
  width: 14px;
}

.grp-path {
  color: var(--text-primary);
  font-size: var(--font-size-caption);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.grp-row.member .grp-path {
  color: var(--accent);
}

.grp-empty {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  padding: var(--space-2);
}

.grp-new {
  border-top: 1px solid var(--border-subtle);
  display: flex;
  gap: var(--space-2);
  padding-top: var(--space-2);
}

.grp-new .input {
  flex: 1;
  min-width: 0;
}
</style>
