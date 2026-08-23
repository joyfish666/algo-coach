<script setup>
import { onMounted } from 'vue'

import ThemeSwitch from './components/ThemeSwitch.vue'
import { useThemeStore } from './stores/theme'

const theme = useThemeStore()
onMounted(() => theme.init())
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div>
        <div class="brand">AlgoCoach</div>
        <nav>
          <RouterLink to="/problems">题库</RouterLink>
          <RouterLink to="/daily">每日一题</RouterLink>
          <RouterLink to="/analyze">分析</RouterLink>
          <RouterLink to="/settings">设置</RouterLink>
        </nav>
      </div>
      <div class="sidebar-footer">
        <ThemeSwitch />
      </div>
    </aside>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 220px;
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
  font-size: 20px;
  font-weight: 700;
  padding: 0 var(--space-3) var(--space-6);
}

nav {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

nav a {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-card);
  color: var(--text-primary);
  font-weight: 500;
}

nav a.router-link-active {
  background: var(--bg-primary);
  color: var(--accent);
}

.sidebar-footer {
  padding-top: var(--space-4);
}

.content {
  flex: 1;
  min-width: 0;
}
</style>
