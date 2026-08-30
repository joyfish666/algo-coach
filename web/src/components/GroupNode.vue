<script setup>
import { computed, ref } from 'vue'

import { copyText } from '../utils/clipboard'
import { useGroupsStore } from '../stores/groups'
import { useI18nStore } from '../stores/i18n'
import { useToastStore } from '../stores/toast'

// Recursive tree node for the /groups page. Script-setup SFCs may reference
// themselves by filename, so <GroupNode> inside the template recurses.
// All actions go straight through the groups store (each mutation re-fetches
// the tiny document), so the node holds only local UI state: which inline
// editor is open and the two-step delete confirmation.
const props = defineProps({
  group: { type: Object, required: true },
  // Map slug -> problem cache row (missing rows render as "unresolved")
  problemIndex: { type: Map, required: true },
})

// a clipboard-refused export surfaces its code one level up, where the
// page-level fallback box lives; recursive children re-emit the same event
const emit = defineEmits(['export-fallback'])

const store = useGroupsStore()
const i18n = useI18nStore()
const toast = useToastStore()

const editing = ref(false)
const editName = ref('')
const creating = ref(false)
const childName = ref('')
const addingProblem = ref(false)
const query = ref('')
const confirmingDelete = ref(false)

const children = computed(() => store.childrenOf(props.group.id))
const siblings = computed(() => store.childrenOf(props.group.parent || null))
const myIndex = computed(() => siblings.value.findIndex((g) => g.id === props.group.id))

// collapse state lives in the shared store (persisted to localStorage) so a
// deep link can expand ancestors before scrolling to the target
const collapsed = computed(() => store.isCollapsed(props.group.id))
const markedCount = computed(() => (props.group.marked || []).length)
const markedSet = computed(() => new Set(props.group.marked || []))

function isMarked(slug) {
  return markedSet.value.has(slug)
}

async function toggleMark(slug) {
  try {
    await store.toggleMarked(props.group.id, slug)
  } catch (err) {
    fail(err)
  }
}

const rows = computed(() =>
  props.group.slugs.map((slug) => ({ slug, row: props.problemIndex.get(slug) || null }))
)

const moveTargets = computed(() =>
  store.groups.filter((g) => g.id !== props.group.id && !store.subtreeIds(props.group.id).has(g.id))
)

const suggestions = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return []
  const out = []
  for (const row of props.problemIndex.values()) {
    if (out.length >= 8) break
    const hay = `${row.frontend_id || ''} ${row.title_cn || ''} ${row.title_en || ''} ${row.slug}`
      .toLowerCase()
    if (hay.includes(needle)) out.push(row)
  }
  return out
})

function fail(err) {
  toast.error({ text: err.message || String(err) })
}

function startRename() {
  editName.value = props.group.name
  editing.value = true
}

async function submitRename() {
  const name = editName.value.trim()
  if (!name) return
  try {
    await store.rename(props.group.id, name)
    editing.value = false
  } catch (err) {
    fail(err)
  }
}

async function submitChild() {
  const name = childName.value.trim()
  if (!name) return
  try {
    await store.create(name, props.group.id)
    childName.value = ''
    creating.value = false
  } catch (err) {
    fail(err)
  }
}

async function addProblem(row) {
  try {
    await store.addSlugs(props.group.id, [row.slug])
  } catch (err) {
    fail(err)
  }
}

async function removeItem(slug) {
  try {
    await store.removeSlug(props.group.id, slug)
  } catch (err) {
    fail(err)
  }
}

async function moveItem(index, delta) {
  const target = index + delta
  if (target < 0 || target >= props.group.slugs.length) return
  const order = [...props.group.slugs]
  ;[order[index], order[target]] = [order[target], order[index]]
  try {
    await store.reorder(props.group.id, order)
  } catch (err) {
    fail(err)
  }
}

async function moveGroup(delta) {
  try {
    await store.move(props.group.id, props.group.parent, myIndex.value + delta)
  } catch (err) {
    fail(err)
  }
}

async function changeParent(event) {
  const parent = event.target.value || null
  try {
    await store.move(props.group.id, parent, null)
  } catch (err) {
    fail(err)
  }
}

async function removeGroup() {
  if (!confirmingDelete.value) {
    confirmingDelete.value = true
    return
  }
  try {
    await store.remove(props.group.id)
  } catch (err) {
    fail(err)
  }
}

async function exportOne() {
  try {
    const code = await store.exportCode([props.group.id])
    const copied = await copyText(code)
    if (copied) {
      toast.success({ text: i18n.t('groups_export_done') })
    } else {
      toast.error({ text: i18n.t('groups_export_copy_failed') })
      emit('export-fallback', code)
    }
  } catch (err) {
    fail(err)
  }
}
</script>

<template>
  <div class="gnode" :id="`group-${group.id}`" data-testid="group-node">
    <div class="gnode-head">
      <button
        class="icon-btn chevron"
        :class="{ collapsed }"
        type="button"
        :title="collapsed ? i18n.t('groups_expand') : i18n.t('groups_collapse')"
        :aria-expanded="collapsed ? 'false' : 'true'"
        data-testid="group-collapse"
        @click="store.toggleCollapsed(group.id)"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      <button class="gnode-name-btn" type="button" data-testid="group-name" @click="store.toggleCollapsed(group.id)">
        <span class="gnode-name">{{ group.name }}</span>
      </button>
      <span class="gnode-count" data-testid="group-count">
        {{ i18n.t('groups_items_count', { count: group.slugs.length }) }}
        <span v-if="markedCount" class="gnode-marked-count">
          · {{ i18n.t('groups_marked_count', { count: markedCount }) }}
        </span>
      </span>
      <span class="gnode-actions">
        <button class="icon-btn" type="button" :title="i18n.t('groups_add_problem')" data-testid="group-add-problem" @click="addingProblem = !addingProblem; query = ''">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
        </button>
        <button class="icon-btn" type="button" :title="i18n.t('groups_add_child')" data-testid="group-add-child" @click="creating = !creating; childName = ''">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 7.5a2 2 0 0 1 2-2h3.6l2 2h7.4a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" /><path d="M12 10.5v5M9.5 13h5" /></svg>
        </button>
        <button class="icon-btn" type="button" :title="i18n.t('groups_rename')" data-testid="group-rename" @click="startRename">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m4 20 .8-3.2L16.6 5a2.1 2.1 0 0 1 3 3L7.8 19.8z" /><path d="m14.5 6.5 3 3" /></svg>
        </button>
        <button class="icon-btn" type="button" :title="i18n.t('groups_move_up')" :disabled="myIndex <= 0" @click="moveGroup(-1)">↑</button>
        <button class="icon-btn" type="button" :title="i18n.t('groups_move_down')" :disabled="myIndex >= siblings.length - 1" @click="moveGroup(1)">↓</button>
        <select
          class="select gnode-move"
          :title="i18n.t('groups_move')"
          data-testid="group-move"
          :value="group.parent || ''"
          @change="changeParent"
        >
          <option value="">{{ i18n.t('groups_move_root') }}</option>
          <option v-for="target in moveTargets" :key="target.id" :value="target.id">
            {{ store.pathOf(target.id) }}
          </option>
        </select>
        <button class="icon-btn" type="button" :title="i18n.t('groups_export')" data-testid="group-export" @click="exportOne">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 14V4M8.5 7.5 12 4l3.5 3.5" /><path d="M5 13v5.5a1.5 1.5 0 0 0 1.5 1.5h11a1.5 1.5 0 0 0 1.5-1.5V13" /></svg>
        </button>
        <button
          class="icon-btn"
          :class="{ danger: confirmingDelete }"
          type="button"
          :title="confirmingDelete ? i18n.t('groups_delete_confirm') : i18n.t('groups_delete')"
          data-testid="group-delete"
          @click="removeGroup"
          @blur="confirmingDelete = false"
        >
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M9.5 7V5h5v2M6.5 7l.8 12.5h9.4L17.5 7" /><path d="M10 11v5.5M14 11v5.5" /></svg>
        </button>
      </span>
    </div>

    <div v-show="!collapsed" class="gnode-body">
      <div v-if="editing" class="gnode-edit">
      <input v-model="editName" class="input" type="text" data-testid="group-rename-input" @keydown.enter="submitRename" @keydown.esc="editing = false" />
      <button class="btn btn-primary btn-sm" type="button" :disabled="!editName.trim()" @click="submitRename">{{ i18n.t('save') }}</button>
      <button class="btn btn-ghost btn-sm" type="button" @click="editing = false">{{ i18n.t('dismiss') }}</button>
    </div>

    <div v-if="creating" class="gnode-edit">
      <input v-model="childName" class="input" type="text" :placeholder="i18n.t('groups_new_group_placeholder')" data-testid="group-child-input" @keydown.enter="submitChild" @keydown.esc="creating = false" />
      <button class="btn btn-primary btn-sm" type="button" :disabled="!childName.trim()" @click="submitChild">{{ i18n.t('groups_add_child') }}</button>
      <button class="btn btn-ghost btn-sm" type="button" @click="creating = false">{{ i18n.t('dismiss') }}</button>
    </div>

    <div v-if="addingProblem" class="gnode-edit gnode-search">
      <input v-model="query" class="input" type="search" :placeholder="i18n.t('problems_search_placeholder')" data-testid="group-problem-search" />
      <div v-if="suggestions.length" class="gnode-suggest">
        <button
          v-for="row in suggestions"
          :key="row.slug"
          type="button"
          class="gnode-suggest-row"
          :data-testid="`suggest-${row.slug}`"
          @click="addProblem(row); query = ''"
        >
          <span class="mono pid">{{ row.frontend_id }}</span>
          <span class="sname">{{ row.title_cn || row.title_en || row.slug }}</span>
        </button>
      </div>
      <p v-else-if="query.trim()" class="gnode-suggest-empty">{{ i18n.t('no_match') }}</p>
    </div>

    <ul class="gnode-items">
      <li v-for="(item, index) in rows" :key="item.slug" class="gnode-item" :class="{ marked: isMarked(item.slug) }">
        <RouterLink v-if="item.row" :to="`/problem/${item.slug}`" class="item-link">
          <span class="item-seq mono">{{ index + 1 }}.</span>
          <span class="mono pid">{{ item.row.frontend_id }}</span>
          <span class="sname">{{ item.row.title_cn || item.row.title_en || item.slug }}</span>
        </RouterLink>
        <span v-else class="item-unknown" :title="i18n.t('groups_unknown_hint')" data-testid="group-unknown-item">
          <span class="item-seq mono">{{ index + 1 }}.</span>
          <code class="mono">{{ item.slug }}</code>
          <span class="chip chip-unsupported">{{ i18n.t('groups_unknown_problem') }}</span>
        </span>
        <span class="item-actions">
          <button
            class="icon-btn mark-btn"
            :class="{ 'mark-active': isMarked(item.slug) }"
            type="button"
            :title="isMarked(item.slug) ? i18n.t('groups_unmark') : i18n.t('groups_mark')"
            data-testid="item-mark"
            @click="toggleMark(item.slug)"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" :fill="isMarked(item.slug) ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M7 4.5h10a.9.9 0 0 1 .9.9V20l-5.9-3.4L6.1 20V5.4a.9.9 0 0 1 .9-.9z" />
            </svg>
          </button>
          <button class="icon-btn" type="button" :disabled="index === 0" @click="moveItem(index, -1)">↑</button>
          <button class="icon-btn" type="button" :disabled="index === rows.length - 1" @click="moveItem(index, 1)">↓</button>
          <button class="icon-btn" type="button" data-testid="item-remove" @click="removeItem(item.slug)">×</button>
        </span>
      </li>
      <li v-if="!rows.length" class="gnode-empty-hint">{{ i18n.t('groups_no_items') }}</li>
    </ul>

    <div v-if="children.length" class="gnode-children">
      <GroupNode
        v-for="child in children"
        :key="child.id"
        :group="child"
        :problem-index="problemIndex"
        @export-fallback="(code) => emit('export-fallback', code)"
      />
    </div>
    </div>
  </div>
</template>

<style scoped>
.gnode {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  padding: var(--space-3) var(--space-4);
}

.gnode-children {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-2);
  padding-left: var(--space-5);
  border-left: 2px solid var(--border-subtle);
}

.gnode-head {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.chevron svg {
  transition: transform 0.15s ease;
}

.chevron.collapsed svg {
  transform: rotate(-90deg);
}

.gnode-name-btn {
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  font: inherit;
  padding: 0;
}

.gnode-name-btn:hover .gnode-name {
  color: var(--accent);
}

.gnode-name {
  font-weight: 600;
}

.gnode-count {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
}

.gnode-marked-count {
  color: var(--accent);
}

.gnode-actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin-left: auto;
}

.icon-btn {
  align-items: center;
  background: transparent;
  border: none;
  border-radius: var(--space-1);
  color: var(--gray-neutral);
  cursor: pointer;
  display: inline-flex;
  font-size: var(--font-size-body);
  line-height: 1;
  padding: 2px 4px;
}

.icon-btn:hover:not(:disabled) {
  background: var(--bg-secondary);
  color: var(--accent);
}

.icon-btn:disabled {
  cursor: default;
  opacity: 0.35;
}

.icon-btn.danger,
.icon-btn.danger:hover {
  color: var(--danger, #d33);
}

.gnode-move {
  max-width: 180px;
  font-size: var(--font-size-caption);
}

.gnode-edit {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.gnode-edit .input {
  flex: 1;
  min-width: 140px;
}

.gnode-search {
  position: relative;
}

.gnode-suggest {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  left: 0;
  position: absolute;
  right: 0;
  top: 100%;
  z-index: 30;
}

.gnode-suggest-row {
  align-items: center;
  background: transparent;
  border: none;
  cursor: pointer;
  display: flex;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  text-align: left;
  width: 100%;
}

.gnode-suggest-row:hover {
  background: var(--bg-secondary);
}

.gnode-suggest-empty {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  padding: var(--space-2);
}

.gnode-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  list-style: none;
  margin: var(--space-2) 0 0;
  padding: 0;
}

.gnode-item {
  align-items: center;
  display: flex;
  gap: var(--space-2);
}

.item-link {
  align-items: center;
  color: var(--text-primary);
  display: flex;
  gap: var(--space-2);
  min-width: 0;
  overflow: hidden;
}

/* the position IS the practice plan: keep it visible at a glance */
.item-seq {
  color: var(--gray-neutral);
  flex-shrink: 0;
  font-size: var(--font-size-caption);
  min-width: 24px;
  text-align: right;
}

.item-link:hover .sname {
  color: var(--accent);
}

.pid {
  color: var(--gray-neutral);
  flex-shrink: 0;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--font-size-caption);
  min-width: 48px;
}

.sname {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-unknown {
  align-items: center;
  color: var(--gray-neutral);
  display: flex;
  gap: var(--space-2);
  min-width: 0;
}

.item-actions {
  display: flex;
  gap: var(--space-1);
  margin-left: auto;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.gnode-item:hover .item-actions,
.gnode-item:focus-within .item-actions {
  opacity: 1;
}

/* key-problem emphasis: bolder title + accent sequence number - reads as
   "this one matters" without turning rows into colored blocks */
.gnode-item.marked .sname {
  font-weight: 650;
}

.gnode-item.marked .item-seq {
  color: var(--accent);
  font-weight: 600;
}

.gnode-item.marked .item-actions {
  opacity: 1;
}

.icon-btn.mark-active,
.icon-btn.mark-active:hover {
  color: var(--accent);
}

.gnode-empty-hint {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
}

/* deep-link flash from the workbench meta-row chips */
.gnode.flash {
  animation: gnode-flash 2s ease;
}

@keyframes gnode-flash {
  0%, 60% {
    border-color: var(--accent);
  }
}
</style>
