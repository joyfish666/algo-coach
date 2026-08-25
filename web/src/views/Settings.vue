<script setup>
import { onMounted, ref } from 'vue'

import LanguageSwitch from '../components/LanguageSwitch.vue'
import PageHeader from '../components/PageHeader.vue'
import ThemeSwitch from '../components/ThemeSwitch.vue'
import { useRouter } from 'vue-router'

import { api } from '../api'
import { debugEnabled, setDebugEnabled } from '../debug'
import { purgeAllSnapshots } from '../snapshots'
import { useI18nStore } from '../stores/i18n'
import { useStatusStore } from '../stores/status'

const i18n = useI18nStore()
const status = useStatusStore()
const router = useRouter()

const codingLang = ref('cpp')
const cookieConfigured = ref(null)
const saving = ref(false)
const savedAt = ref('')
const saveError = ref('')

const clearingData = ref(false)
const clearMessage = ref('')
const clearConfirmInput = ref('')

const languages = [
  { value: 'cpp', label: 'C++' },
  { value: 'python3', label: 'Python 3' },
  { value: 'java', label: 'Java' },
]

onMounted(async () => {
  try {
    const settings = await api.getSettings()
    codingLang.value = settings.default_language || 'cpp'
    cookieConfigured.value = Boolean(settings.configured)
  } catch {
    cookieConfigured.value = null
  }
})

async function saveDefaultLanguage() {
  if (saving.value) return
  saving.value = true
  saveError.value = ''
  try {
    await api.putSettings({ default_language: codingLang.value })
    savedAt.value = i18n.formatDateTime(new Date())
  } catch (err) {
    saveError.value = err.message || String(err)
  } finally {
    saving.value = false
  }
}

function clearConfirmReady() {
  return clearConfirmInput.value.trim() === 'DELETE'
}

async function eraseAllData() {
  if (clearingData.value || !clearConfirmReady()) return
  clearingData.value = true
  clearMessage.value = ''
  try {
    await api.clearLocalData()
    // drafts live in localStorage, outside the backend data dir; without
    // purging them here the old code would resurface after re-setup
    purgeAllSnapshots()
    clearMessage.value = i18n.t('cleared_ok')
    await status.refresh()
    setTimeout(() => router.push('/setup'), 900)
  } catch (err) {
    clearMessage.value =
      (err.payload && err.payload.detail) ||
      (err.payload && err.payload.error && err.payload.error.message) ||
      err.message
  } finally {
    clearingData.value = false
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
        <span class="field-label">{{ i18n.t('settings_theme') }}</span>
        <ThemeSwitch />
      </div>
      <div class="row">
        <label class="use-debug">
          <input
            type="checkbox"
            :checked="debugEnabled"
            data-testid="debug-toggle"
            @change="setDebugEnabled($event.target.checked)"
          />
          <span>{{ i18n.t('debug_title') }}</span>
        </label>
        <span class="hint-text">{{ i18n.t('debug_hint') }}</span>
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
        <span v-if="savedAt && !saveError" class="saved-hint" data-testid="saved-hint">
          {{ i18n.t('saved_ok') }} · {{ savedAt }}
        </span>
        <span v-if="saveError" class="error-hint" data-testid="save-error">{{ saveError }}</span>
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
        <!-- settings request failed: state unknown, never fabricate one -->
        <span v-else class="placeholder">—</span>
        <RouterLink class="btn btn-ghost btn-sm" to="/setup" data-testid="update-cookie-link">
          {{ i18n.t('update_cookie') }}
        </RouterLink>
      </div>
    </div>

    <div class="card">
      <h2>{{ i18n.t('data_section') }}</h2>
      <p class="hint-text">{{ i18n.t('data_path_hint') }}</p>
      <code class="data-path" data-testid="data-dir">{{ status.dataDir || '—' }}</code>
      <p class="hint-text">{{ i18n.t('clear_confirm_typed') }}</p>
      <div class="row">
        <input
          v-model="clearConfirmInput"
          class="input confirm-input mono"
          type="text"
          spellcheck="false"
          autocomplete="off"
          placeholder="DELETE"
          data-testid="clear-confirm-input"
        />
        <button
          class="btn btn-ghost danger"
          type="button"
          :disabled="clearingData || !clearConfirmReady()"
          data-testid="clear-data-btn"
          @click="eraseAllData"
        >
          {{ clearingData ? i18n.t('clearing') : i18n.t('clear_all') }}
        </button>
        <span v-if="clearMessage" class="saved-hint" data-testid="clear-message">{{ clearMessage }}</span>
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

.error-hint {
  color: var(--text-primary);
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.confirm-input {
  max-width: 180px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.btn-sm {
  padding: var(--space-1) var(--space-4);
}

.use-debug {
  align-items: center;
  display: inline-flex;
  font-size: var(--font-size-body);
  gap: var(--space-2);
}

.hint-text {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
}

.data-path {
  background: var(--bg-secondary);
  border-radius: var(--space-1);
  display: inline-block;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--font-size-caption);
  margin-bottom: var(--space-4);
  padding: var(--space-1) var(--space-2);
  word-break: break-all;
}

.danger:hover:not(:disabled) {
  border-color: var(--text-primary);
}
</style>
