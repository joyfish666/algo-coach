import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/problems' },
  { path: '/setup', name: 'setup', component: () => import('../views/Setup.vue') },
  { path: '/problems', name: 'problems', component: () => import('../views/Problems.vue') },
  {
    path: '/problem/:qid',
    name: 'problem-detail',
    component: () => import('../views/ProblemDetail.vue'),
    props: true,
  },
  { path: '/daily', name: 'daily', component: () => import('../views/Daily.vue') },
  { path: '/analyze', name: 'analyze', component: () => import('../views/Analyze.vue') },
  { path: '/settings', name: 'settings', component: () => import('../views/Settings.vue') },
  { path: '/:pathMatch(.*)*', redirect: '/problems' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  if (to.path === '/setup') return true
  try {
    const response = await fetch('/api/status')
    if (!response.ok) return true
    const status = await response.json()
    if (!status.configured) return { path: '/setup' }
  } catch {
    return true
  }
  return true
})

export default router
