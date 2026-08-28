import { createRouter, createWebHistory } from 'vue-router'

import { useI18nStore } from '../stores/i18n'
import { useStatusStore } from '../stores/status'

const routes = [
  { path: '/', redirect: '/problems' },
  {
    path: '/setup',
    name: 'setup',
    component: () => import('../views/Setup.vue'),
    meta: { titleKey: 'setup_title' },
  },
  {
    path: '/problems',
    name: 'problems',
    component: () => import('../views/Problems.vue'),
    meta: { titleKey: 'problems_title' },
  },
  {
    path: '/problem/:qid',
    name: 'problem-detail',
    component: () => import('../views/ProblemDetail.vue'),
    props: true,
    meta: { titleKey: null },
  },
  {
    path: '/daily',
    name: 'daily',
    component: () => import('../views/Daily.vue'),
    meta: { titleKey: 'daily_title' },
  },
  {
    path: '/history',
    name: 'history',
    component: () => import('../views/History.vue'),
    meta: { titleKey: 'history_title' },
  },
  {
    path: '/analyze',
    name: 'analyze',
    component: () => import('../views/Analyze.vue'),
    meta: { titleKey: 'analyze_title' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../views/Settings.vue'),
    meta: { titleKey: 'settings_title' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/problems' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    // without this the window scroll carried across navigations: scrolling
    // deep into the problem list, then opening Settings, landed mid-page
    return savedPosition || { top: 0 }
  },
})

// /api/status decides the /setup redirect, but "configured" only changes via
// setup/erase - awaiting a fresh round-trip on every navigation used to block
// each click (up to the 45s fetch deadline) behind a backend that had stopped
// answering. Fresh-enough cached state lets navigation proceed immediately
// while one background refresh revalidates.
const STATUS_MAX_AGE_MS = 30000

router.beforeEach(async (to) => {
  if (to.path === '/setup') return true
  const status = useStatusStore()
  if (status.loaded && Date.now() - status.refreshedAt < STATUS_MAX_AGE_MS) {
    status.refresh()
  } else {
    await status.refresh()
  }
  if (status.loaded && status.reachable && !status.configured) {
    return { path: '/setup' }
  }
  return true
})

router.afterEach((to) => {
  const i18n = useI18nStore()
  const key = to.meta?.titleKey
  document.title = key ? `${i18n.t(key)} · AlgoCoach` : 'AlgoCoach'
})

// Lazy-loaded chunks are content-hashed, so a tab left open across a
// redeploy references chunk names that no longer exist: the dynamic import
// rejected and the failed navigation was swallowed - every click silently
// did nothing until a manual reload. A hard navigation re-fetches index.html
// with the new chunk graph.
router.onError((error, to) => {
  if (/dynamically imported module|module script|Importing a module script/i.test(error?.message || '')) {
    window.location.assign(to?.fullPath || '/')
  }
})

export default router
