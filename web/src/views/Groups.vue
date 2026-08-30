<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import GroupNode from '../components/GroupNode.vue'
import PageHeader from '../components/PageHeader.vue'
import { api } from '../api'
import { copyText } from '../utils/clipboard'
import { useGroupsStore } from '../stores/groups'
import { useI18nStore } from '../stores/i18n'
import { useToastStore } from '../stores/toast'

// Groups management page: one page renders the whole tree (recursion lives
// in GroupNode). The problem cache is loaded once for display (id/title per
// slug) and for the add-problem search; slugs missing from the cache render
// as "unresolved" instead of being hidden, so a shared plan imported before
// a sync still shows its shape.
const i18n = useI18nStore()
const groups = useGroupsStore()
const toast = useToastStore()
const route = useRoute()

const problemIndex = ref(new Map())
const problemsLoaded = ref(false)
const problemsError = ref('')

const groupsError = ref('')
const importOpen = ref(false)
const importCode = ref('')
const importing = ref(false)
const creating = ref(false)
const newName = ref('')
const exportedCode = ref('')

const rootGroups = computed(() => groups.rootGroups)
// first paint only: later mutations re-fetch silently (loaded stays true)
const initializing = computed(
  () => !problemsLoaded.value || (groups.loading && !groups.loaded)
)

async function loadProblems() {
  try {
    const data = await api.getProblems()
    const index = new Map()
    for (const row of data.problems || []) index.set(row.slug, row)
    problemIndex.value = index
  } catch (err) {
    problemsError.value = err.message || String(err)
  } finally {
    problemsLoaded.value = true
  }
}

async function reload() {
  groupsError.value = ''
  try {
    await groups.refresh()
  } catch (err) {
    groupsError.value = err.message || String(err)
  }
}

async function submitCreate() {
  const name = newName.value.trim()
  if (!name) return
  try {
    await groups.create(name, null)
    newName.value = ''
    creating.value = false
  } catch (err) {
    toast.error({ text: err.message || String(err) })
  }
}

async function submitImport() {
  const code = importCode.value.trim()
  if (!code || importing.value) return
  importing.value = true
  try {
    const result = await groups.importCode(code)
    importCode.value = ''
    importOpen.value = false
    toast.success({ text: i18n.t('groups_import_done', { count: result?.created ?? 0 }) })
  } catch (err) {
    toast.error({ text: err.message || String(err) })
  } finally {
    importing.value = false
  }
}

async function exportShare(ids) {
  try {
    const code = await groups.exportCode(ids)
    const copied = await copyText(code)
    if (copied) {
      toast.success({ text: i18n.t('groups_export_done') })
    } else {
      // clipboard refused: surface the code in a box instead of losing it
      exportedCode.value = code
      toast.error({ text: i18n.t('groups_export_copy_failed') })
    }
  } catch (err) {
    toast.error({ text: err.message || String(err) })
  }
}

onMounted(async () => {
  loadProblems()
  await reload()
  // deep link from the workbench meta-row chips: /groups?group=<id>
  const focusId = route.query.group
  if (focusId) {
    // expand the target and all its collapsed ancestors before scrolling
    groups.expandTo(String(focusId))
    await nextTick()
    const el = document.getElementById(`group-${focusId}`)
    if (el) {
      el.scrollIntoView({ block: 'center' })
      el.classList.add('flash')
      setTimeout(() => el.classList.remove('flash'), 2200)
    }
  }
})
</script>

<template>
  <section class="page">
    <PageHeader :title="i18n.t('groups_title')" :subtitle="i18n.t('groups_subtitle')">
      <template #actions>
        <div class="header-actions">
          <button
            class="btn btn-ghost"
            type="button"
            data-testid="groups-import-btn"
            @click="importOpen = !importOpen"
          >
            {{ i18n.t('groups_import') }}
          </button>
          <button
            class="btn btn-ghost"
            type="button"
            :disabled="!groups.groups.length"
            data-testid="groups-export-btn"
            @click="exportShare(null)"
          >
            {{ i18n.t('groups_export_all') }}
          </button>
          <button
            class="btn btn-primary"
            type="button"
            data-testid="groups-create-btn"
            @click="creating = !creating; newName = ''"
          >
            {{ i18n.t('groups_create') }}
          </button>
        </div>
      </template>
    </PageHeader>

    <div v-if="importOpen" class="card io-card">
      <textarea
        v-model="importCode"
        class="input io-area"
        rows="3"
        :placeholder="i18n.t('groups_import_placeholder')"
        data-testid="groups-import-area"
      ></textarea>
      <button
        class="btn btn-primary"
        type="button"
        :disabled="!importCode.trim() || importing"
        data-testid="groups-import-submit"
        @click="submitImport"
      >
        {{ i18n.t('groups_import') }}
      </button>
    </div>

    <div v-if="exportedCode" class="card io-card" data-testid="groups-export-box">
      <textarea readonly class="input io-area mono-area" rows="3" :value="exportedCode"></textarea>
      <button class="btn btn-ghost" type="button" @click="exportedCode = ''">
        {{ i18n.t('dismiss') }}
      </button>
    </div>

    <div v-if="creating" class="card io-card">
      <input
        v-model="newName"
        class="input"
        type="text"
        :placeholder="i18n.t('groups_new_group_placeholder')"
        data-testid="groups-create-name"
        @keydown.enter="submitCreate"
      />
      <button
        class="btn btn-primary"
        type="button"
        :disabled="!newName.trim()"
        data-testid="groups-create-submit"
        @click="submitCreate"
      >
        {{ i18n.t('groups_create') }}
      </button>
    </div>

    <p v-if="problemsError" class="card problems-warn">{{ problemsError }}</p>

    <div v-if="initializing" class="group-list" data-testid="groups-skeleton">
      <div v-for="index in 4" :key="index" class="skeleton skeleton-row"></div>
    </div>

    <div v-else-if="groupsError" class="card empty-state">
      <p>{{ groupsError }}</p>
      <button class="btn btn-ghost" type="button" @click="reload">
        {{ i18n.t('retry') }}
      </button>
    </div>

    <div v-else-if="!rootGroups.length" class="card empty-state" data-testid="groups-empty">
      <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3.5 7.5a2 2 0 0 1 2-2h3.6l2 2h7.4a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" />
        <path d="M12 10.5v5M9.5 13h5" />
      </svg>
      <p class="empty-title">{{ i18n.t('groups_empty') }}</p>
      <button class="btn btn-primary" type="button" @click="creating = true">
        {{ i18n.t('groups_create') }}
      </button>
    </div>

    <div v-else class="group-list" data-testid="groups-tree">
      <GroupNode
        v-for="root in rootGroups"
        :key="root.id"
        :group="root"
        :problem-index="problemIndex"
        @export-fallback="(code) => (exportedCode = code)"
      />
    </div>
  </section>
</template>

<style scoped>
.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.io-card {
  align-items: flex-start;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.io-area {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  resize: vertical;
  width: 100%;
}

.problems-warn {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  margin-bottom: var(--space-4);
}

.group-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.skeleton-row {
  height: 56px;
}

.empty-title {
  font-weight: 600;
}
</style>
