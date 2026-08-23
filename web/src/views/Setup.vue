<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import PageHeader from '../components/PageHeader.vue'
import ThemeSwitch from '../components/ThemeSwitch.vue'
import { api } from '../api'
import { useI18nStore } from '../stores/i18n'
import { useStatusStore } from '../stores/status'

const i18n = useI18nStore()
const status = useStatusStore()
const router = useRouter()

const step = ref(1)

const advancedMode = ref(false)
const sessionValue = ref('')
const csrfValue = ref('')
const cookieInput = ref('')
const validating = ref(false)
const cookieOk = ref(false)
const cookieError = ref('')

const llmKey = ref('')
const llmBaseUrl = ref('')
const llmModel = ref('')

const codingLang = ref('cpp')
const finishing = ref(false)
const done = ref(false)
const finishError = ref('')

const languages = [
  { value: 'cpp', label: 'C++' },
  { value: 'python3', label: 'Python 3' },
  { value: 'java', label: 'Java' },
]

const steps = computed(() => [
  i18n.t('setup_step_cookie'),
  i18n.t('setup_step_llm'),
  i18n.t('setup_step_prefs'),
])

const composedCookie = computed(() => {
  if (advancedMode.value) return cookieInput.value.trim()
  const parts = []
  if (sessionValue.value.trim()) parts.push(`LEETCODE_SESSION=${sessionValue.value.trim()}`)
  if (csrfValue.value.trim()) parts.push(`csrftoken=${csrfValue.value.trim()}`)
  return parts.join('; ')
})

function resetCookieState() {
  cookieOk.value = false
  cookieError.value = ''
}

async function validateAndNext() {
  if (!composedCookie.value || validating.value) return
  validating.value = true
  cookieError.value = ''
  try {
    await api.validateCookie(composedCookie.value)
    cookieOk.value = true
    setTimeout(() => {
      if (cookieOk.value) goStep(2)
    }, 400)
  } catch (err) {
    cookieOk.value = false
    cookieError.value =
      (err.payload && err.payload.error && err.payload.error.message) ||
      err.message ||
      String(err)
  } finally {
    validating.value = false
  }
}

function goStep(target) {
  step.value = target
}

function skipLlm() {
  llmKey.value = ''
  llmBaseUrl.value = ''
  llmModel.value = ''
  goStep(3)
}

function llmProvided() {
  return Boolean(llmKey.value.trim() || llmBaseUrl.value.trim() || llmModel.value.trim())
}

async function finish() {
  if (finishing.value) return
  finishing.value = true
  finishError.value = ''
  const payload = {
    cookie: composedCookie.value,
    default_language: codingLang.value,
  }
  if (llmProvided()) {
    payload.llm_api_key = llmKey.value.trim()
    payload.llm_base_url = llmBaseUrl.value.trim()
    payload.llm_model = llmModel.value.trim()
  }
  try {
    await api.putSettings(payload)
    await status.refresh()
    done.value = true
    setTimeout(() => router.push('/problems'), 800)
  } catch (err) {
    finishError.value =
      (err.payload && err.payload.error && err.payload.error.message) || err.message || String(err)
  } finally {
    finishing.value = false
  }
}
</script>

<template>
  <section class="page setup-page">
    <PageHeader :title="i18n.t('setup_title')" :subtitle="i18n.t('setup_subtitle')" />

    <div v-if="status.configured" class="card banner-accent already-banner">
      {{ i18n.t('already_configured') }}
    </div>

    <div class="card wizard" data-testid="setup-wizard">
      <ol class="steps">
        <li
          v-for="(label, index) in steps"
          :key="label"
          :class="{ active: step === index + 1, done: step > index + 1 }"
        >
          <span class="step-num">{{ index + 1 }}</span>
          <span class="step-label">{{ label }}</span>
        </li>
      </ol>

      <section v-if="step === 1" class="step-body">
        <div class="mode-tabs">
          <button
            type="button"
            :class="{ active: !advancedMode }"
            @click="advancedMode = false; resetCookieState()"
          >
            {{ i18n.t('setup_mode_simple') }}
          </button>
          <button
            type="button"
            :class="{ active: advancedMode }"
            @click="advancedMode = true; resetCookieState()"
          >
            {{ i18n.t('setup_mode_advanced') }}
          </button>
        </div>

        <template v-if="!advancedMode">
          <p class="guide-text">{{ i18n.t('cookie_guide') }}</p>
          <div class="field">
            <span class="field-label">{{ i18n.t('field_leetcode_session') }}</span>
            <input
              v-model="sessionValue"
              class="input wide mono-input"
              type="password"
              autocomplete="off"
              spellcheck="false"
              data-testid="session-input"
              @input="resetCookieState"
            />
          </div>
          <div class="field">
            <span class="field-label">{{ i18n.t('field_csrftoken') }}</span>
            <input
              v-model="csrfValue"
              class="input wide mono-input"
              type="password"
              autocomplete="off"
              spellcheck="false"
              data-testid="csrf-input"
              @input="resetCookieState"
            />
          </div>
        </template>

        <template v-else>
          <span class="field-label">Cookie</span>
          <textarea
            v-model="cookieInput"
            class="input cookie-input mono"
            rows="4"
            spellcheck="false"
            :placeholder="i18n.t('cookie_hint')"
            data-testid="cookie-input"
            @input="resetCookieState"
          ></textarea>
        </template>

        <p v-if="validating" class="msg">{{ i18n.t('validating') }}</p>
        <p v-else-if="cookieOk" class="msg ok" data-testid="cookie-valid">{{ i18n.t('cookie_valid') }}</p>
        <p v-else-if="cookieError" class="msg bad" data-testid="cookie-error">{{ cookieError }}</p>

        <div class="row-actions">
          <span class="spacer"></span>
          <button
            class="btn btn-primary"
            type="button"
            :disabled="!composedCookie || validating || !cookieOk"
            data-testid="cookie-next"
            @click="goStep(2)"
          >
            {{ i18n.t('next') }}
          </button>
        </div>
      </section>

      <section v-else-if="step === 2" class="step-body">
        <div class="field">
          <span class="field-label">{{ i18n.t('llm_api_key') }}</span>
          <input v-model="llmKey" class="input wide" type="password" autocomplete="off" />
        </div>
        <div class="field">
          <span class="field-label">{{ i18n.t('llm_base_url') }}</span>
          <input v-model="llmBaseUrl" class="input wide" placeholder="https://api.openai.com/v1" />
        </div>
        <div class="field">
          <span class="field-label">{{ i18n.t('llm_model') }}</span>
          <input v-model="llmModel" class="input wide" placeholder="gpt-4o-mini" />
        </div>
        <p class="hint-text">{{ i18n.t('llm_skip_hint') }}</p>

        <div class="row-actions">
          <button class="btn btn-ghost" type="button" @click="goStep(1)">
            {{ i18n.t('back') }}
          </button>
          <span class="spacer"></span>
          <button class="btn btn-ghost" type="button" data-testid="llm-skip" @click="skipLlm">
            {{ i18n.t('skip') }}
          </button>
          <button
            class="btn btn-primary"
            type="button"
            data-testid="llm-next"
            @click="goStep(3)"
          >
            {{ i18n.t('next') }}
          </button>
        </div>
      </section>

      <section v-else class="step-body">
        <div class="field">
          <span class="field-label">{{ i18n.t('settings_coding_lang') }}</span>
          <select v-model="codingLang" class="select" data-testid="default-lang-select">
            <option v-for="item in languages" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </div>
        <div class="field">
          <span class="field-label">{{ i18n.t('settings_appearance') }}</span>
          <ThemeSwitch />
        </div>
        <p v-if="finishError" class="msg bad">{{ finishError }}</p>
        <p v-if="done" class="msg ok" data-testid="setup-done">{{ i18n.t('setup_done') }}</p>

        <div class="row-actions">
          <button class="btn btn-ghost" type="button" :disabled="finishing || done" @click="goStep(2)">
            {{ i18n.t('back') }}
          </button>
          <span class="spacer"></span>
          <button
            class="btn btn-primary"
            type="button"
            :disabled="finishing || done"
            data-testid="finish-btn"
            @click="finish"
          >
            {{ finishing ? i18n.t('finishing') : i18n.t('finish_setup') }}
          </button>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.setup-page {
  max-width: 720px;
}

.already-banner {
  border-color: var(--accent);
  color: var(--text-primary);
  margin-bottom: var(--space-4);
  padding: var(--space-3) var(--space-4);
}

.wizard {
  padding: var(--space-6);
}

.steps {
  display: flex;
  gap: var(--space-2);
  list-style: none;
  margin: 0 0 var(--space-6);
  padding: 0;
}

.steps li {
  align-items: center;
  background: var(--bg-secondary);
  border-radius: var(--radius-pill);
  color: var(--gray-neutral);
  display: flex;
  flex: 1;
  font-size: var(--font-size-caption);
  gap: var(--space-2);
  justify-content: center;
  padding: var(--space-1) var(--space-3);
}

.steps li.active {
  background: var(--accent);
  color: #ffffff;
}

.steps li.done {
  color: var(--accent);
}

.step-num {
  font-weight: 700;
}

.cookie-input {
  width: 100%;
  resize: vertical;
}

.mode-tabs {
  display: flex;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  overflow: hidden;
  margin-bottom: var(--space-4);
}

.mode-tabs button {
  background: transparent;
  border: none;
  color: var(--gray-neutral);
  flex: 1;
  font-size: var(--font-size-caption);
  padding: var(--space-2) var(--space-3);
}

.mode-tabs button + button {
  border-left: 1px solid var(--border-subtle);
}

.mode-tabs button.active {
  background: var(--accent);
  color: #ffffff;
}

.guide-text {
  background: var(--bg-secondary);
  border-radius: var(--radius-card);
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  line-height: 1.8;
  margin: 0 0 var(--space-4);
  padding: var(--space-3) var(--space-4);
}

.mono-input {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--font-size-caption);
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--font-size-caption);
}

.msg {
  font-size: var(--font-size-caption);
  margin: var(--space-3) 0 0;
}

.msg.ok {
  color: var(--accent);
}

.msg.bad {
  color: var(--text-primary);
  font-weight: 500;
}

.row-actions {
  align-items: center;
  display: flex;
  gap: var(--space-3);
  margin-top: var(--space-6);
}

.spacer {
  flex: 1;
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-bottom: var(--space-4);
}

.input.wide {
  width: 100%;
}

.hint-text {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
}
</style>
