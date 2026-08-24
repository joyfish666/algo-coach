<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import LanguageSwitch from './components/LanguageSwitch.vue'
import ThemeSwitch from './components/ThemeSwitch.vue'
import ToastHost from './components/ToastHost.vue'
import {
  debugClear,
  debugCopyToClipboard,
  debugEnabled,
  debugEntries,
  setDebugEnabled,
} from './debug'
import { useI18nStore } from './stores/i18n'
import { useStatusStore } from './stores/status'
import { useSyncStore } from './stores/sync'
import { useThemeStore } from './stores/theme'

const i18n = useI18nStore()
const status = useStatusStore()
const sync = useSyncStore()
const theme = useThemeStore()
const route = useRoute()

const authExpired = ref(false)
const copied = ref(false)

async function copyDebugLogs() {
  const ok = await debugCopyToClipboard()
  if (ok) {
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  }
}

function onAuthExpired() {
  authExpired.value = true
}

onMounted(() => {
  theme.init()
  status.refresh().then(() => sync.adoptFromStatus(status.sync))
  window.addEventListener('algocoach:auth-expired', onAuthExpired)
})

onBeforeUnmount(() => {
  window.removeEventListener('algocoach:auth-expired', onAuthExpired)
})

watch(
  () => route.path,
  (path) => {
    if (path === '/setup') authExpired.value = false
  }
)

watch(
  () => i18n.lang,
  (lang) => {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
  },
  { immediate: true }
)
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div>
        <div class="brand">
          <svg
            class="brand-mark"
            viewBox="0 0 24 24"
            width="24"
            height="24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M8.5 7 4 12l4.5 5" />
            <path d="m15.5 7 4.5 5-4.5 5" />
            <path d="m13.2 5.5-2.4 13" />
          </svg>
          <span>AlgoCoach</span>
        </div>
        <nav>
          <RouterLink to="/problems" class="nav-item">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M4 6h16M4 12h16M4 18h10" />
            </svg>
            <span>{{ i18n.t('nav_problems') }}</span>
          </RouterLink>
          <RouterLink to="/daily" class="nav-item">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" />
              <path d="M3.5 9.5h17M8 3v3.5M16 3v3.5" />
            </svg>
            <span>{{ i18n.t('nav_daily') }}</span>
          </RouterLink>
          <RouterLink to="/history" class="nav-item">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4.5 5.5h15v13h-15z" />
              <path d="M7.5 9.5h9M7.5 12.5h9M7.5 15.5h5" />
            </svg>
            <span>{{ i18n.t('nav_history') }}</span>
          </RouterLink>
          <RouterLink to="/analyze" class="nav-item">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M5 20V12M12 20V5.5M19 20v-5" />
            </svg>
            <span>{{ i18n.t('nav_analyze') }}</span>
          </RouterLink>
          <RouterLink to="/settings" class="nav-item">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M4 7h16M4 12h16M4 17h16" />
              <circle cx="9" cy="7" r="1.6" />
              <circle cx="15" cy="12" r="1.6" />
              <circle cx="8" cy="17" r="1.6" />
            </svg>
            <span>{{ i18n.t('nav_settings') }}</span>
          </RouterLink>
        </nav>
      </div>
      <div class="sidebar-footer">
        <ThemeSwitch />
        <LanguageSwitch />
        <div v-if="status.version" class="version">v{{ status.version }}</div>
      </div>
    </aside>
    <main class="content">
      <RouterView />
    </main>

    <ToastHost />

    <div v-if="debugEnabled" class="debug-bar" data-testid="debug-bar">
      <span class="debug-count">DEBUG · {{ debugEntries.length }}</span>
      <button class="btn btn-ghost btn-xs" type="button" @click="copyDebugLogs">
        {{ copied ? i18n.t('debug_copied') : i18n.t('debug_copy') }}
      </button>
      <button class="btn btn-ghost btn-xs" type="button" @click="debugClear()">
        {{ i18n.t('debug_clear') }}
      </button>
      <button
        class="btn btn-ghost btn-xs"
        type="button"
        data-testid="debug-off"
        @click="setDebugEnabled(false)"
      >
        {{ i18n.t('debug_off') }}
      </button>
    </div>

    <div v-if="authExpired" class="auth-banner" data-testid="auth-expired-banner">
      <span>{{ i18n.t('cookie_invalid') }}</span>
      <button
        class="btn btn-primary btn-sm"
        type="button"
        data-testid="banner-relogin"
        @click="authExpired = false; $router.push('/setup')"
      >
        {{ i18n.t('action_relogin') }}
      </button>
      <button class="btn btn-ghost btn-sm" type="button" @click="authExpired = false">
        {{ i18n.t('dismiss') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 232px;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  background: var(--bg-secondary);
  padding: var(--space-6) var(--space-4);
}

.brand {
  align-items: center;
  color: var(--text-primary);
  display: flex;
  font-size: var(--font-size-title);
  font-weight: 700;
  gap: var(--space-2);
  padding: 0 var(--space-2) var(--space-6);
}

.brand-mark {
  color: var(--accent);
}

nav {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.nav-item {
  align-items: center;
  border-radius: var(--radius-card);
  color: var(--text-primary);
  display: flex;
  font-weight: 500;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
}

.nav-item:hover {
  background: var(--bg-primary);
}

.nav-item.router-link-active {
  background: var(--bg-primary);
  color: var(--accent);
}

.sidebar-footer {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-top: var(--space-4);
}

.version {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  padding-left: var(--space-1);
}

.content {
  flex: 1;
  min-width: 0;
}

.auth-banner {
  align-items: center;
  backdrop-filter: blur(4px);
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  bottom: var(--space-6);
  box-shadow: var(--shadow-card);
  display: flex;
  gap: var(--space-3);
  left: 50%;
  padding: var(--space-3) var(--space-4);
  position: fixed;
  transform: translateX(-50%);
  z-index: 50;
}

.debug-bar {
  align-items: center;
  background: var(--bg-secondary);
  border: 1px dashed var(--gray-neutral);
  border-radius: var(--radius-pill);
  bottom: var(--space-2);
  display: flex;
  gap: var(--space-2);
  left: var(--space-2);
  padding: var(--space-1) var(--space-2);
  position: fixed;
  z-index: 60;
}

.debug-count {
  color: var(--accent);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px;
}

.btn-xs {
  font-size: 11px;
  padding: 0 var(--space-2);
}
</style>
