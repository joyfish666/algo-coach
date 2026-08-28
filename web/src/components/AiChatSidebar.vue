<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

import { api } from '../api'
import { useI18nStore } from '../stores/i18n'
import { useStatusStore } from '../stores/status'

const props = defineProps({
  qid: { type: String, required: true },
  // lazy getter for the editor buffer; opt-in per question so a long
  // solution is not shipped to the LLM on every casual ask
  getCode: { type: Function, default: null },
})

const i18n = useI18nStore()
// LLM availability comes from /api/status so the panel can guide the user to
// Settings BEFORE a send fails: the workbench used to be the one LLM surface
// without a not-configured gate (analytics had one)
const status = useStatusStore()

if (!status.loaded) {
  status.refresh()
}

const POS_KEY = 'algocoach-ai-pos'

const open = ref(false)
const messages = ref([])
const draft = ref('')
const pending = ref(false)
const attachCode = ref(false)
const listEl = ref(null)
const panelEl = ref(null)

function readPos() {
  try {
    const raw = JSON.parse(localStorage.getItem(POS_KEY))
    if (raw && typeof raw.x === 'number' && typeof raw.y === 'number') return raw
  } catch {
  }
  return null
}

const pos = ref(readPos())

let dragOffset = null

function clamp(x, y) {
  // measure the live panel instead of hardcoding its CSS size, so style and
  // logic can never drift apart when the layout changes
  const width = panelEl.value?.offsetWidth || 340
  const height = panelEl.value?.offsetHeight || 520
  const maxX = window.innerWidth - width - 8
  const maxY = window.innerHeight - height - 8
  return {
    x: Math.min(Math.max(8, x), Math.max(8, maxX)),
    y: Math.min(Math.max(8, y), Math.max(8, maxY)),
  }
}

// a panel dragged on a larger window (or restored from storage after a
// resolution change) must not stay stranded off-screen until the next drag
function reclampToViewport() {
  if (!open.value || !pos.value) return
  pos.value = clamp(pos.value.x, pos.value.y)
}

window.addEventListener('resize', reclampToViewport)

function onGlobalKeydown(event) {
  if (event.key === 'Escape' && !event.isComposing) {
    open.value = false
  }
}

function startDrag(event) {
  if (event.target.closest('.head-actions')) return
  event.preventDefault()
  const rect = panelEl.value?.getBoundingClientRect()
  const fallbackWidth = rect?.width || 340
  const current = rect
    ? { x: rect.left, y: rect.top }
    : { x: window.innerWidth - fallbackWidth - 24, y: 24 }
  dragOffset = { dx: event.clientX - current.x, dy: event.clientY - current.y }
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', endDrag)
}

function onDragMove(event) {
  if (!dragOffset) return
  pos.value = clamp(event.clientX - dragOffset.dx, event.clientY - dragOffset.dy)
}

function endDrag() {
  dragOffset = null
  document.body.style.userSelect = ''
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', endDrag)
  try {
    if (pos.value) localStorage.setItem(POS_KEY, JSON.stringify(pos.value))
  } catch {
  }
}

onBeforeUnmount(() => {
  if (dragOffset) endDrag()
  window.removeEventListener('resize', reclampToViewport)
  window.removeEventListener('keydown', onGlobalKeydown)
})

watch(open, (value) => {
  if (value) {
    reclampToViewport()
    window.addEventListener('keydown', onGlobalKeydown)
  } else {
    window.removeEventListener('keydown', onGlobalKeydown)
  }
})

// the workbench component is reused across /problem/:qid navigations, so a
// qid change would otherwise keep the previous problem's conversation here
// and leak it into the next problem's LLM context
watch(
  () => props.qid,
  () => {
    messages.value = []
    pending.value = false
    draft.value = ''
    attachCode.value = false
  }
)

function clearConversation() {
  if (pending.value || !messages.value.length) return
  messages.value = []
}

async function toggle() {
  open.value = !open.value
}

function scrollToEnd() {
  nextTick(() => {
    if (listEl.value) {
      listEl.value.scrollTop = listEl.value.scrollHeight
    }
  })
}

async function send() {
  const question = draft.value.trim()
  if (!question || pending.value || !status.llmConfigured) return
  const askedQid = props.qid
  draft.value = ''
  messages.value.push({ role: 'user', content: question })
  pending.value = true
  scrollToEnd()
  try {
    // error bubbles are UI feedback, not conversation turns; feeding them
    // back as assistant messages would poison the model's context
    const history = messages.value
      .filter((m) => !m.error)
      .slice(-13, -1)
      .map((m) => ({ role: m.role, content: m.content }))
    const data = await api.ask({
      question,
      history,
      qid: askedQid,
      code: attachCode.value && props.getCode ? props.getCode() : null,
      lang: null,
    })
    if (askedQid !== props.qid) return // user switched problems meanwhile
    messages.value.push({ role: 'assistant', content: data.answer })
  } catch (err) {
    if (askedQid !== props.qid) return
    const message =
      (err.payload && err.payload.detail) ||
      (err.payload && err.payload.error && err.payload.error.message) ||
      err.message
    messages.value.push({ role: 'assistant', content: `⚠️ ${message}`, error: true })
  } finally {
    if (askedQid === props.qid) {
      pending.value = false
      scrollToEnd()
    }
  }
}

function onEnter(event) {
  // IME composition: pressing Enter to confirm candidate characters (how
  // Chinese input is committed) must not send a half-typed draft
  if (event.isComposing || event.keyCode === 229) return
  if (event.shiftKey) return
  event.preventDefault()
  send()
}
</script>

<template>
  <aside
    v-if="open"
    ref="panelEl"
    class="panel card"
    :style="pos ? { left: pos.x + 'px', top: pos.y + 'px', right: 'auto' } : {}"
    data-testid="ai-panel"
  >
    <header class="panel-head" @mousedown="startDrag">
      <h2>{{ i18n.t('ai_title') }}</h2>
      <div class="head-actions">
        <button
          class="clear"
          type="button"
          :title="i18n.t('ai_clear')"
          :disabled="pending || !messages.length"
          data-testid="ai-clear"
          @click="clearConversation"
        >
          {{ i18n.t('ai_clear') }}
        </button>
        <button class="close" type="button" :title="i18n.t('ai_close')" @click="toggle">
          ✕
        </button>
      </div>
    </header>
    <p class="context-hint">{{ i18n.t('ai_context_hint') }}</p>

    <div v-if="!status.llmConfigured" class="llm-hint" data-testid="ai-not-configured">
      <span>{{ i18n.t('ai_not_configured_hint') }}</span>
      <RouterLink class="llm-hint-link" to="/settings">{{ i18n.t('nav_settings') }}</RouterLink>
    </div>

    <label v-if="getCode" class="attach-row" data-testid="attach-code">
      <input v-model="attachCode" type="checkbox" />
      <span>{{ i18n.t('attach_code') }}</span>
    </label>

    <div ref="listEl" class="messages">
      <p v-if="!messages.length && !pending" class="empty">{{ i18n.t('ai_placeholder') }}</p>
      <div
        v-for="(message, index) in messages"
        :key="index"
        class="bubble"
        :class="[message.role, { error: message.error }]"
      >
        {{ message.content }}
      </div>
      <div v-if="pending" class="bubble assistant pending">…</div>
    </div>

    <footer class="composer">
      <textarea
        v-model="draft"
        class="input composer-input"
        rows="2"
        :placeholder="i18n.t('ai_placeholder')"
        :disabled="pending"
        @keydown.enter="onEnter"
      ></textarea>
      <button
        class="btn btn-primary btn-sm"
        type="button"
        :disabled="pending || !draft.trim() || !status.llmConfigured"
        data-testid="ai-send"
        @click="send"
      >
        {{ i18n.t('ai_send') }}
      </button>
    </footer>
  </aside>

  <button
    v-else
    class="fab"
    type="button"
    :title="i18n.t('ai_title')"
    data-testid="ai-open"
    @click="toggle"
  >
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 3.5c2.2 2.8 4.4 4.2 7.5 5-3.1 0.8-5.3 2.2-7.5 5-2.2-2.8-4.4-4.2-7.5-5 3.1-0.8 5.3-2.2 7.5-5z" />
      <path d="M18.5 15.5c0.9 1.2 1.8 2.1 3.2 2.1-1.3 0.3-2.3 0.9-3.2 2.1-0.9-1.2-1.9-1.8-3.2-2.1 1.3-0.3 2.3-0.9 3.2-2.1z" />
    </svg>
    <span class="fab-label">{{ i18n.t('ai_open') }}</span>
  </button>
</template>

<style scoped>
.fab {
  align-items: center;
  background: var(--accent);
  border: none;
  border-radius: var(--radius-pill);
  bottom: var(--space-6);
  box-shadow: var(--shadow-card);
  color: #ffffff;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-3);
  position: fixed;
  right: var(--space-6);
  z-index: 39;
}

.fab-label {
  font-size: 10px;
  font-weight: 600;
}

.panel {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 120px);
  max-width: 380px;
  position: fixed;
  right: var(--space-6);
  top: var(--space-6);
  width: 340px;
  z-index: 40;
}

.panel-head {
  align-items: center;
  cursor: move;
  display: flex;
  justify-content: space-between;
  user-select: none;
}

.panel-head h2 {
  font-size: var(--font-size-title);
  margin-bottom: 0;
}

.head-actions {
  align-items: center;
  display: flex;
  gap: var(--space-2);
}

.clear {
  background: transparent;
  border: none;
  color: var(--gray-neutral);
  cursor: pointer;
  font-size: var(--font-size-caption);
}

.clear:hover:not(:disabled) {
  color: var(--danger);
}

.clear:disabled {
  cursor: default;
  opacity: 0.5;
}

.close {
  background: transparent;
  border: none;
  color: var(--gray-neutral);
  cursor: pointer;
  font-size: var(--font-size-title);
}

.context-hint {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  margin: var(--space-1) 0 0;
}

.llm-hint {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  color: var(--text-primary);
  display: flex;
  flex-direction: column;
  font-size: var(--font-size-caption);
  gap: var(--space-2);
  margin-top: var(--space-3);
  padding: var(--space-3);
}

.llm-hint-link {
  color: var(--accent);
  font-weight: 600;
}

.attach-row {
  align-items: center;
  color: var(--gray-neutral);
  cursor: pointer;
  display: flex;
  font-size: var(--font-size-caption);
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.messages {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  display: flex;
  flex-direction: column;
  flex: 1;
  gap: var(--space-2);
  margin-top: var(--space-3);
  overflow-y: auto;
  padding: var(--space-3);
}

.empty {
  color: var(--gray-neutral);
  font-size: var(--font-size-caption);
  text-align: center;
}

.bubble {
  border-radius: var(--radius-card);
  font-size: var(--font-size-body);
  line-height: 1.55;
  max-width: 88%;
  padding: var(--space-2) var(--space-3);
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble.user {
  align-self: flex-end;
  background: var(--accent);
  color: #ffffff;
}

.bubble.assistant {
  align-self: flex-start;
  background: var(--bg-secondary);
}

.bubble.pending {
  animation: pulse 1s infinite;
  color: var(--gray-neutral);
}

@keyframes pulse {
  50% {
    opacity: 0.4;
  }
}

.composer {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-3);
}

.composer-input {
  resize: none;
  width: 100%;
}

.btn-sm {
  align-self: flex-end;
}
</style>
