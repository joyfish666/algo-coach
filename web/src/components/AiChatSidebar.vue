<script setup>
import { nextTick, ref, watch } from 'vue'

import { api } from '../api'
import { userFacingError } from '../utils/errors'
import { makeMarkdown } from '../utils/markdown'
import { useFloatingPanel } from '../utils/floatingPanel'
import { STORAGE_KEYS } from '../utils/storage'
import { useI18nStore } from '../stores/i18n'
import { useStatusStore } from '../stores/status'

const props = defineProps({
  qid: { type: String, required: true },
  // lazy getter for the editor buffer; opt-in per question so a long
  // solution is not shipped to the LLM on every casual ask
  getCode: { type: Function, default: null },
  // editor language for the attached-code context label ("Current code
  // (python3):" instead of a meaningless "text"); the backend only reads
  // it alongside code
  codeLang: { type: String, default: '' },
})

const i18n = useI18nStore()
// LLM availability comes from /api/status so the panel can guide the user to
// Settings BEFORE a send fails: the workbench used to be the one LLM surface
// without a not-configured gate (analytics had one)
const status = useStatusStore()

if (!status.loaded) {
  status.refresh()
}

// Every OpenAI-compatible model replies in Markdown (bold, lists, code
// fences) - plain-text interpolation leaked the markers into the chat as
// literal "**". breaks:true suits chat-style line wrapping (the statement
// and report renderers keep CommonMark paragraph rules).
const md = makeMarkdown({ breaks: true })

const { open, pos, panelEl, toggle, startDrag } = useFloatingPanel({
  id: 'ai',
  posKey: STORAGE_KEYS.panelPos,
})

const messages = ref([])
const draft = ref('')
const pending = ref(false)
const attachCode = ref(false)
const listEl = ref(null)

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
      lang: props.codeLang || null,
    })
    if (askedQid !== props.qid) return // user switched problems meanwhile
    // content stays raw for the LLM history; html is the rendered form
    messages.value.push({
      role: 'assistant',
      content: data.answer,
      html: md.render(data.answer),
    })
  } catch (err) {
    if (askedQid !== props.qid) return
    const message = userFacingError(err)
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
  <button
    class="fab ai-fab"
    :class="{ active: open }"
    type="button"
    :title="i18n.t('ai_title')"
    :aria-label="i18n.t('ai_title')"
    :aria-pressed="open ? 'true' : 'false'"
    data-testid="ai-open"
    @click="toggle"
  >
    {{ i18n.t('ai_open') }}
  </button>

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
        <!-- assistant replies carry rendered markdown (html:false-escaped);
             user drafts and error notices stay verbatim text -->
        <div v-if="message.html" class="md" v-html="message.html"></div>
        <template v-else>{{ message.content }}</template>
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
</template>

<style scoped>
/* top slot of the button stack; the notes circle sits one slot below (see
   NotesPanel) so the two form one vertical group on the right edge */
.ai-fab {
  bottom: calc(var(--space-6) + 64px);
}

.fab {
  align-items: center;
  background: var(--accent);
  border: none;
  border-radius: 50%;
  box-shadow: var(--shadow-card);
  color: #ffffff;
  cursor: pointer;
  display: flex;
  font-size: 17px;
  font-weight: 700;
  height: 52px;
  justify-content: center;
  letter-spacing: 0.02em;
  position: fixed;
  right: var(--space-6);
  width: 52px;
  z-index: 39;
}

.fab:hover,
.fab.active {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}

.panel {
  display: flex;
  flex-direction: column;
  /* the default corner hosts the two circular buttons below (top slot starts
     ~140px up): stop the panel short of them so it never covers its own
     toggle; a dragged position is the user's call */
  height: calc(100vh - 176px);
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

/* rendered markdown must not inherit the plain-text pre-wrap (block-level
   elements would gain phantom whitespace between tags) */
.bubble .md {
  white-space: normal;
}

.md :deep(p),
.md :deep(ul),
.md :deep(ol) {
  margin: var(--space-2) 0;
}

.md :deep(p:first-child),
.md :deep(ul:first-child),
.md :deep(ol:first-child),
.md :deep(pre:first-child) {
  margin-top: 0;
}

.md :deep(p:last-child),
.md :deep(ul:last-child),
.md :deep(ol:last-child),
.md :deep(pre:last-child) {
  margin-bottom: 0;
}

.md :deep(ul),
.md :deep(ol) {
  padding-left: var(--space-6);
}

.md :deep(pre) {
  background: var(--bg-secondary);
  border-radius: var(--radius-card);
  overflow-x: auto;
  padding: var(--space-3);
}

.md :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--font-size-caption);
}

.md :deep(pre code) {
  font-size: inherit;
}

/* assistant answers frequently carry comparison tables - same grid treatment
   as the statement renderer */
.md :deep(table) {
  border-collapse: collapse;
  margin: var(--space-2) 0;
}

.md :deep(th),
.md :deep(td) {
  border: 1px solid var(--border-subtle);
  padding: var(--space-1) var(--space-2);
  text-align: left;
  word-break: break-word;
}

.md :deep(th) {
  background: var(--bg-secondary);
  font-weight: 600;
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
