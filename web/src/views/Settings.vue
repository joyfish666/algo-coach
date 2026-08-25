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

// AI/LLM 配置独立于 Cookie：在这里单独填写与保存
const llmKey = ref('')
const llmBaseUrl = ref('')
const llmModel = ref('')
const hasLlmKey = ref(false)
const savingLlm = ref(false)
const llmSavedAt = ref('')
const llmError = ref('')

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
    llmBaseUrl.value = settings.llm_base_url || ''
    llmModel.value = settings.llm_model || ''
    hasLlmKey.value = Boolean(settings.llm_api_key_masked)
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

// 留空 Key 表示不修改已保存的值；接口地址与模型按当前输入保存
async function saveLlm() {
  if (savingLlm.value) return
  savingLlm.value = true
  llmError.value = ''
  try {
    const payload = {
      llm_base_url: llmBaseUrl.value.trim(),
      llm_model: llmModel.value.trim(),
    }
    if (llmKey.value.trim()) payload.llm_api_key = llmKey.value.trim()
    const updated = await api.putSettings(payload)
    hasLlmKey.value = Boolean(updated.llm_api_key_masked)
    llmBaseUrl.value = updated.llm_base_url || ''
    llmModel.value = updated.llm_model || ''
    llmKey.value = ''
    llmSavedAt.value = i18n.formatDateTime(new Date())
  } catch (err) {
    llmError.value =
      (err.payload && err.payload.error && err.payload.error.message) || err.message || String(err)
  } finally {
    savingLlm.value = false
  }
}

// 连通性探测：用表单当前值（未填的回退到已保存配置），不必先保存
const testingLlm = ref(false)
const llmTestOk = ref('')
const llmTestError = ref('')

async function testLlm() {
  if (testingLlm.value) return
  testingLlm.value = true
  llmTestOk.value = ''
  llmTestError.value = ''
  const payload = {}
  if (llmKey.value.trim()) payload.llm_api_key = llmKey.value.trim()
  if (llmBaseUrl.value.trim()) payload.llm_base_url = llmBaseUrl.value.trim()
  if (llmModel.value.trim()) payload.llm_model = llmModel.value.trim()
  const startedAt = performance.now()
  try {
    const result = await api.testLlm(payload)
    const elapsed = Math.round(performance.now() - startedAt)
    llmTestOk.value = i18n.t('llm_test_ok', { model: result.model, ms: elapsed })
  } catch (err) {
    llmTestError.value =
      (err.payload && err.payload.error && err.payload.error.message) || err.message || String(err)
  } finally {
    testingLlm.value = false
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
      <h2>{{ i18n.t('settings_llm') }}</h2>
      <div class="row">
        <span v-if="cookieConfigured !== null" class="chip" :class="{ 'chip-ok': hasLlmKey }" data-testid="llm-chip">
          {{ hasLlmKey ? i18n.t('llm_enabled') : i18n.t('llm_disabled') }}
        </span>
        <span class="hint-text">{{ i18n.t('llm_hint') }}</span>
      </div>
      <div class="field">
        <span class="field-label">{{ i18n.t('llm_api_key') }}</span>
        <input
          v-model="llmKey"
          class="input llm-input"
          type="password"
          autocomplete="off"
          data-testid="llm-key-input"
        />
        <span v-if="hasLlmKey" class="hint-text">{{ i18n.t('llm_key_saved_hint') }}</span>
      </div>
      <div class="field">
        <span class="field-label">{{ i18n.t('llm_base_url') }}</span>
        <input
          v-model="llmBaseUrl"
          class="input llm-input"
          placeholder="https://api.deepseek.com"
          data-testid="llm-url-input"
        />
      </div>
      <div class="field">
        <span class="field-label">{{ i18n.t('llm_model') }}</span>
        <input
          v-model="llmModel"
          class="input llm-input"
          placeholder="deepseek-v4-flash"
          data-testid="llm-model-input"
        />
      </div>
      <div class="row">
        <button class="btn btn-primary" type="button" :disabled="savingLlm" data-testid="llm-save" @click="saveLlm">
          {{ i18n.t('save') }}
        </button>
        <button
          class="btn btn-ghost"
          type="button"
          :disabled="testingLlm"
          data-testid="llm-test"
          @click="testLlm"
        >
          {{ testingLlm ? i18n.t('llm_testing') : i18n.t('llm_test') }}
        </button>
        <span v-if="llmSavedAt && !llmError" class="saved-hint" data-testid="llm-saved-hint">
          {{ i18n.t('saved_ok') }} · {{ llmSavedAt }}
        </span>
        <span v-if="llmError" class="error-hint" data-testid="llm-error">{{ llmError }}</span>
      </div>
      <p v-if="llmTestOk" class="test-msg ok" data-testid="llm-test-ok">{{ llmTestOk }}</p>
      <p v-else-if="llmTestError" class="test-msg bad" data-testid="llm-test-error">{{ llmTestError }}</p>
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

.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-bottom: var(--space-4);
}

.llm-input {
  max-width: 420px;
}

.test-msg {
  font-size: var(--font-size-caption);
  margin: var(--space-2) 0 0;
}

.test-msg.ok {
  color: var(--ok);
}

.test-msg.bad {
  color: var(--danger);
  word-break: break-all;
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
