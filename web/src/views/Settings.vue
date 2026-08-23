<script setup>
import { onMounted, ref } from 'vue'

import LanguageSwitch from '../components/LanguageSwitch.vue'
import PageHeader from '../components/PageHeader.vue'
import ThemeSwitch from '../components/ThemeSwitch.vue'
import { useI18nStore } from '../stores/i18n'

const i18n = useI18nStore()

const codingLang = ref('cpp')
const cookieConfigured = ref(null)
const saving = ref(false)
const savedAt = ref('')

const languages = [
  { value: 'cpp', label: 'C++' },
  { value: 'python3', label: 'Python 3' },
  { value: 'java', label: 'Java' },
]

onMounted(async () => {
  try {
    const response = await fetch('/api/settings')
    if (!response.ok) return
    const settings = await response.json()
    codingLang.value = settings.default_language || 'cpp'
    cookieConfigured.value = Boolean(settings.configured)
  } catch {
    cookieConfigured.value = null
  }
})

async function saveDefaultLanguage() {
  saving.value = true
  try {
    const response = await fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ default_language: codingLang.value }),
    })
    if (response.ok) {
      savedAt.value = new Date().toLocaleTimeString()
    }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="page">
    <PageHeader :title="i18n.t('settings_title')" :subtitle="i18n.t('settings_subtitle')" />

    <div class="card">
      <h2>{{ i18n.t('settings_appearance') }}</h2>
      <div class="row">
        <span class="field-label">{{ i18n.t('settings_interface_lang') }}</span>
        <LanguageSwitch />
      </div>
      <div class="row" data-testid="theme-switch-row">
        <span class="field-label">{{ i18n.t('theme_system') }}</span>
        <ThemeSwitch />
      </div>
    </div>

    <div class="card">
      <h2>{{ i18n.t('settings_coding_lang') }}</h2>
      <div class="row">
        <select v-model="codingLang" class="select" data-testid="coding-lang-select">
          <option v-for="item in languages" :key="item.value" :value="item.value">
            {{ item.label }}
          </option>
        </select>
        <button class="btn btn-primary" type="button" :disabled="saving" @click="saveDefaultLanguage">
          {{ i18n.t('save') }}
        </button>
        <span v-if="savedAt" class="saved-hint" data-testid="saved-hint">
          {{ i18n.t('saved_ok') }} · {{ savedAt }}
        </span>
      </div>
    </div>

    <div class="card">
      <h2>{{ i18n.t('settings_account') }}</h2>
      <div class="row">
        <span
          v-if="cookieConfigured !== null"
          class="chip"
          :class="{ 'chip-ok': cookieConfigured }"
          data-testid="cookie-chip"
        >
          {{ cookieConfigured ? i18n.t('cookie_configured') : i18n.t('cookie_missing') }}
        </span>
        <span v-else class="placeholder">API: 127.0.0.1:8000</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.field-label {
  margin-bottom: 0;
  min-width: 120px;
}

.saved-hint {
  color: var(--accent);
  font-size: var(--font-size-caption);
}
</style>
