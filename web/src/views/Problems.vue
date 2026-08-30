<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PageHeader from '../components/PageHeader.vue'
import ProblemCard from '../components/ProblemCard.vue'
import { api } from '../api'
import { useI18nStore } from '../stores/i18n'
import { useStatusStore } from '../stores/status'
import { useSyncStore } from '../stores/sync'
import { useToastStore } from '../stores/toast'
import { collectTags, filterProblems, paginate, pickRandom, sortByMode } from '../utils/problems'
import { STORAGE_KEYS, readStorage, writeStorage } from '../utils/storage'

const PAGE_SIZE = 50
const DENSITY_KEY = STORAGE_KEYS.density

const i18n = useI18nStore()
const status = useStatusStore()
const sync = useSyncStore()
const toast = useToastStore()
const route = useRoute()
const router = useRouter()

const problems = ref([])
const syncedAt = ref(null)
const loadingList = ref(true)
const listError = ref('')

const keyword = ref('')
const difficulty = ref('')
const tagSlug = ref('')
const statusFilter = ref('')
const sortMode = ref('id')
const dense = ref(readDensity())

const page = ref(1)

function readDensity() {
  return readStorage(DENSITY_KEY) === 'dense'
}

function toggleDensity() {
  dense.value = !dense.value
  writeStorage(DENSITY_KEY, dense.value ? 'dense' : 'cozy')
}

const tagOptions = computed(() => collectTags(problems.value))

const filtered = computed(() =>
  filterProblems(problems.value, {
    keyword: keyword.value,
    difficulty: difficulty.value,
    tagSlug: tagSlug.value,
    status: statusFilter.value,
  })
)

const paged = computed(() => paginate(sortByMode(filtered.value, sortMode.value), page.value, PAGE_SIZE))

// The URL query is the source of truth for the filters it carries: applying
// only present keys used to leave stale filters active after navigating back
// to a bare /problems (URL said "no filter", the list stayed filtered).
function applyRouteQuery() {
  if (route.path !== '/problems') return
  const q = route.query
  keyword.value = q.q !== undefined ? String(q.q) : ''
  const diff = String(q.difficulty || '')
  difficulty.value = ['easy', 'medium', 'hard'].includes(diff) ? diff : ''
  tagSlug.value = q.tag !== undefined ? String(q.tag) : ''
}

watch(() => route.fullPath, applyRouteQuery, { immediate: true })

// any filter/sort change restarts pagination
watch([keyword, difficulty, tagSlug, statusFilter, sortMode], () => (page.value = 1))

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

// the backend finished a run this view is interested in -> refresh the cache
// view; done/failed announcements themselves come from the toast channel
watch(
  () => sync.phase,
  (phase, prev) => {
    if ((phase === 'done' || phase === 'failed') && prev === 'running') {
      loadProblems()
      status.refresh()
    }
  }
)

function goRandom() {
  const row = pickRandom(filtered.value)
  if (row) router.push(`/problem/${row.slug}`)
}

async function onToggleFavorite({ slug, next }) {
  // optimistic update; the row object is shared with the card via props
  const row = problems.value.find((item) => item.slug === slug)
  if (!row) return
  const previous = row.favorite
  row.favorite = next
  try {
    await api.putFavorite(slug, next)
  } catch (err) {
    row.favorite = previous
    toast.error({ text: err.message || String(err) })
  }
}

onMounted(() => {
  // adopt an in-flight backend sync (page reload / first visit mid-sync);
  // no-op when idle. status was already refreshed by the router guard.
  sync.adoptFromStatus(status.sync)
  loadProblems()
})
</script>

<template>
  <section class="page">
    <PageHeader :title="i18n.t('problems_title')" :subtitle="i18n.t('problems_subtitle')">
      <template #actions>
        <div class="header-actions">
          <button
            class="btn btn-primary"
            type="button"
            :disabled="sync.running || !status.reachable"
            data-testid="sync-btn"
            @click="sync.start()"
          >
            {{ sync.label }}
          </button>
          <span v-if="sync.running" class="sync-note">{{ i18n.t('sync_eta') }}</span>
          <span v-else-if="syncedAt" class="last-synced">
            {{ i18n.t('last_synced') }}: {{ i18n.formatDateTime(syncedAt) }}
          </span>
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
      <select v-model="statusFilter" class="select" data-testid="status-select">
        <option value="">{{ i18n.t('status_filter_all') }}</option>
        <option value="solved">{{ i18n.t('status_solved') }}</option>
        <option value="attempted">{{ i18n.t('status_attempted') }}</option>
        <option value="todo">{{ i18n.t('status_todo') }}</option>
        <option value="favorite">{{ i18n.t('filter_favorite') }}</option>
      </select>
      <select v-model="difficulty" class="select" data-testid="difficulty-select">
        <option value="">{{ i18n.t('diff_all') }}</option>
        <option value="easy">{{ i18n.t('diff_easy') }}</option>
        <option value="medium">{{ i18n.t('diff_medium') }}</option>
        <option value="hard">{{ i18n.t('diff_hard') }}</option>
      </select>
      <select v-model="tagSlug" class="select tag-select" data-testid="tag-select">
        <option value="">{{ i18n.t('tag_all') }}</option>
        <option v-for="tag in tagOptions" :key="tag.slug" :value="tag.slug">
          {{ tag.name_zh || tag.name_en }} ({{ tag.count }})
        </option>
      </select>
      <select v-model="sortMode" class="select" data-testid="sort-select">
        <option value="id">{{ i18n.t('sort_id') }}</option>
        <option value="recent">{{ i18n.t('sort_recent') }}</option>
      </select>
      <button
        class="btn btn-ghost"
        type="button"
        :disabled="!filtered.length"
        data-testid="random-btn"
        @click="goRandom"
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <rect x="3.5" y="3.5" width="17" height="17" rx="4" />
          <circle cx="8.5" cy="8.5" r="1.15" fill="currentColor" stroke="none" />
          <circle cx="15.5" cy="15.5" r="1.15" fill="currentColor" stroke="none" />
          <circle cx="12" cy="12" r="1.15" fill="currentColor" stroke="none" />
          <circle cx="15.5" cy="8.5" r="1.15" fill="currentColor" stroke="none" />
          <circle cx="8.5" cy="15.5" r="1.15" fill="currentColor" stroke="none" />
        </svg>
        {{ i18n.t('action_random') }}
      </button>
      <button
        class="btn btn-ghost"
        type="button"
        data-testid="density-btn"
        @click="toggleDensity"
      >
        {{ dense ? i18n.t('density_cozy') : i18n.t('density_compact') }}
      </button>
    </div>

    <div v-if="loadingList" class="problem-list" data-testid="skeleton-list">
      <div v-for="index in 8" :key="index" class="skeleton skeleton-row"></div>
    </div>

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
      <button class="btn btn-primary" type="button" :disabled="sync.running" @click="sync.start()">
        {{ i18n.t('sync_now') }}
      </button>
    </div>

    <template v-else>
      <div class="problem-list" :class="{ dense }" data-testid="problem-list">
        <ProblemCard
          v-for="row in paged.rows"
          :key="row.slug"
          :row="row"
          @toggle-favorite="onToggleFavorite"
        />
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

.toolbar {
  /* one row, always: the tag <select> used to size itself to its longest
     option text (hundreds of tag names after a full sync), which ate the
     whole row and pushed the density toggle onto a second line. The filter
     controls get compact fixed widths so the row fits without scrolling. */
  display: flex;
  flex-wrap: nowrap;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  padding: var(--space-4);
}

.search {
  /* the only flexible item; leftover space stays at the row's end so the
     density toggle never sits against the card's right edge */
  flex: 1 1 auto;
  min-width: 120px;
  max-width: 360px;
}

.toolbar > .select {
  /* compact uniform width instead of the option-driven intrinsic one; the
     closed select clips its label, dropdown lists still show full text */
  flex: 0 1 auto;
  min-width: 0;
  width: 100px;
}

/* widest filter: shows the selected tag name */
.toolbar > .tag-select {
  width: 136px;
}

.toolbar > .btn {
  flex: none;
}

.problem-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.skeleton-row {
  height: 52px;
}

/* compact reading mode: trade breathing room for scan density */
.dense {
  gap: var(--space-1);
}

.dense :deep(.pcard) {
  padding: var(--space-1) var(--space-3);
}

.dense :deep(.ptags),
.dense :deep(.pstatus) {
  display: none;
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
