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
})

router.beforeEach(async (to) => {
  if (to.path === '/setup') return true
  const status = useStatusStore()
  await status.refresh()
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

export default router
