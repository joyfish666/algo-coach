<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import PageHeader from '../components/PageHeader.vue'
import ProblemCard from '../components/ProblemCard.vue'
import { api } from '../api'
import { useI18nStore } from '../stores/i18n'
import { useStatusStore } from '../stores/status'
import { collectTags, filterProblems, paginate, sortByMode } from '../utils/problems'

const PAGE_SIZE = 50

const i18n = useI18nStore()
const status = useStatusStore()
const route = useRoute()

const problems = ref([])
const syncedAt = ref(null)
const loadingList = ref(true)
const listError = ref('')

const keyword = ref('')
const difficulty = ref('')
const tagSlug = ref('')
const sortMode = ref('id')

const page = ref(1)

const syncing = ref(false)
const syncFetched = ref(0)
const syncTotal = ref(null)
const syncMessage = ref('')
const syncErrorText = ref('')
let pollTimer = null

const tagOptions = computed(() => collectTags(problems.value))

function applyRouteQuery() {
  if (route.path !== '/problems') return
  const q = route.query
  if (q.q !== undefined) keyword.value = String(q.q)
  const diff = String(q.difficulty || '')
  if (['easy', 'medium', 'hard'].includes(diff)) difficulty.value = diff
  if (q.tag !== undefined) tagSlug.value = String(q.tag)
}

watch(() => route.fullPath, applyRouteQuery, { immediate: true })

watch(keyword, () => (page.value = 1))
watch(difficulty, () => (page.value = 1))
watch(tagSlug, () => (page.value = 1))

const filtered = computed(() =>
  filterProblems(problems.value, {
    keyword: keyword.value,
    difficulty: difficulty.value,
    tagSlug: tagSlug.value,
  })
)

const paged = computed(() => paginate(sortByMode(filtered.value, sortMode.value), page.value, PAGE_SIZE))

watch(keyword, () => (page.value = 1))
watch(difficulty, () => (page.value = 1))
watch(tagSlug, () => (page.value = 1))

async function loadProblems() {
  loadingList.value = true
  listError.value = ''
  try {
    const data = await api.getProblems()
    problems.value = data.problems || []
    syncedAt.value = data.synced_at
  } catch (err) {
    listError.value = err.message
  } finally {
    loadingList.value = false
  }
}

function syncLabel() {
  if (!syncing.value) return i18n.t('sync_now')
  const total = syncTotal.value
  if (!total) return i18n.t('sync_running', { fetched: syncFetched.value, total: '?' })
  return i18n.t('sync_running', { fetched: syncFetched.value, total })
}

async function startSync() {
  if (syncing.value) return
  syncErrorText.value = ''
  syncMessage.value = ''
  syncing.value = true
  syncFetched.value = 0
  syncTotal.value = null
  try {
    try {
      await api.startSync()
    } catch (err) {
      if (err.status !== 409) throw err
    }
    pollTimer = setInterval(pollSyncProgress, 1000)
    await pollSyncProgress()
  } catch (err) {
    syncing.value = false
    clearInterval(pollTimer)
    syncErrorText.value = err.message || String(err)
  }
}

async function pollSyncProgress() {
  try {
    const progress = await api.getSyncProgress()
    syncFetched.value = progress.fetched || 0
    syncTotal.value = progress.total ?? null
    if (!progress.running) {
      clearInterval(pollTimer)
      pollTimer = null
      syncing.value = false
      if (progress.error) {
        syncErrorText.value = `${i18n.t('sync_error')}: ${progress.error}`
      } else {
        syncMessage.value = i18n.t('sync_done')
        setTimeout(() => (syncMessage.value = ''), 4000)
      }
      await loadProblems()
      status.refresh()
    }
  } catch {
    /* transient polling failure; keep trying until interval cleared */
  }
}

onMounted(loadProblems)
onBeforeUnmount(() => clearInterval(pollTimer))
</script>

<template>
  <section class="page">
    <PageHeader :title="i18n.t('problems_title')" :subtitle="i18n.t('problems_subtitle')">
      <template #actions>
        <div class="header-actions">
          <button
            class="btn btn-primary"
            type="button"
            :disabled="syncing || !status.reachable"
            data-testid="sync-btn"
            @click="startSync"
          >
            {{ syncLabel() }}
          </button>
          <span v-if="syncing" class="sync-note">{{ i18n.t('sync_eta') }}</span>
          <span v-else-if="syncMessage" class="sync-done" data-testid="sync-done">{{ syncMessage }}</span>
          <span v-else-if="syncedAt" class="last-synced">
            {{ i18n.t('last_synced') }}: {{ new Date(syncedAt).toLocaleString() }}
          </span>
          <span v-else-if="syncErrorText" class="sync-error">{{ syncErrorText }}</span>
        </div>
      </template>
    </PageHeader>

    <div class="card toolbar">
      <input
        v-model="keyword"
        class="input search"
        type="search"
        :placeholder="i18n.t('problems_search_placeholder')"
        data-testid="search-input"
      />
      <select v-model="difficulty" class="select" data-testid="difficulty-select">
        <option value="">{{ i18n.t('diff_all') }}</option>
        <option value="easy">{{ i18n.t('diff_easy') }}</option>
        <option value="medium">{{ i18n.t('diff_medium') }}</option>
        <option value="hard">{{ i18n.t('diff_hard') }}</option>
      </select>
      <select v-model="tagSlug" class="select" data-testid="tag-select">
        <option value="">{{ i18n.t('tag_all') }}</option>
        <option v-for="tag in tagOptions" :key="tag.slug" :value="tag.slug">
          {{ tag.name_zh || tag.name_en }} ({{ tag.count }})
        </option>
      </select>
      <select v-model="sortMode" class="select" data-testid="sort-select">
        <option value="id">{{ i18n.t('sort_id') }}</option>
        <option value="recent">{{ i18n.t('sort_recent') }}</option>
      </select>
    </div>

    <div v-if="loadingList" class="card empty-state">{{ i18n.t('loading_problem') }}</div>

    <div v-else-if="listError" class="card empty-state">
      <p>{{ listError }}</p>
      <button class="btn btn-ghost" type="button" @click="loadProblems">
        {{ i18n.t('retry') }}
      </button>
    </div>

    <div v-else-if="!problems.length" class="card empty-state" data-testid="empty-problems">
      <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
        <path d="M4 6h16M4 12h16M4 18h10" />
      </svg>
      <p class="empty-title">{{ i18n.t('empty_title') }}</p>
      <p>{{ i18n.t('empty_body') }}</p>
      <button class="btn btn-primary" type="button" :disabled="syncing" @click="startSync">
        {{ i18n.t('sync_now') }}
      </button>
    </div>

    <template v-else>
      <div class="problem-list" data-testid="problem-list">
        <ProblemCard v-for="row in paged.rows" :key="row.slug" :row="row" />
        <p v-if="!paged.rows.length" class="card empty-state no-match" data-testid="no-match">
          {{ i18n.t('no_match') }}
        </p>
      </div>

      <div class="pager" v-if="paged.pages > 1">
        <button
          class="btn btn-ghost btn-sm"
          type="button"
          :disabled="paged.current <= 1"
          data-testid="prev-page"
          @click="page -= 1"
        >
          {{ i18n.t('prev_page') }}
        </button>
        <span class="page-info">
          {{
            i18n.t('page_info', {
              current: paged.current,
              pages: paged.pages,
              total: filtered.length,
            })
          }}
        </span>
        <button
          class="btn btn-ghost btn-sm"
          type="button"
          :disabled="paged.current >= paged.pages"
          data-testid="next-page"
          @click="page += 1"
        >
          {{ i18n.t('next_page') }}
        </button>
      </div>
      <div class="pager pager-single" v-else>
        <span class="page-info">{{ i18n.t('page_info', { current: 1, pages: 1, total: filtered.length }) }}</span>
      </div>
    </template>
  </section>
</template>

<style scoped>
.header-actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.sync-note,
.last-synced {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
}

.sync-done {
  color: var(--accent);
  font-size: var(--font-size-caption);
}

.sync-error {
  color: var(--text-primary);
  font-size: var(--font-size-caption);
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  padding: var(--space-4);
}

.search {
  flex: 1;
  min-width: 220px;
}

.problem-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.no-match {
  padding: var(--space-6);
}

.pager {
  align-items: center;
  display: flex;
  justify-content: space-between;
  margin-top: var(--space-4);
}

.pager-single {
  justify-content: center;
}

.page-info {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
}
</style>
