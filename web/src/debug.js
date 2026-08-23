import { ref } from 'vue'

const KEY = 'algocoach-debug'
const MAX_ENTRIES = 300

function initialEnabled() {
  try {
    if (localStorage.getItem(KEY) === '1') return true
  } catch {
  }
  return new URLSearchParams(window.location.search).has('debug')
}

export const debugEnabled = ref(initialEnabled())
export const debugEntries = ref([])
let installed = false

function stamp() {
  return new Date().toLocaleTimeString()
}

function push(level, text) {
  debugEntries.value.push(`[${stamp()}] [${level}] ${text}`)
  if (debugEntries.value.length > MAX_ENTRIES) {
    debugEntries.value.splice(0, debugEntries.value.length - MAX_ENTRIES)
  }
}

function install() {
  if (installed) return
  installed = true

  window.addEventListener('error', (event) => {
    push('error', `${event.message} @ ${event.filename}:${event.lineno}:${event.colno}`)
  })

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason
    const text = reason instanceof Error ? `${reason.message}\n${reason.stack || ''}` : String(reason)
    push('unhandled-rejection', text.slice(0, 800))
  })

  const originalError = console.error.bind(console)
  console.error = (...args) => {
    push(
      'console.error',
      args
        .map((a) => (a instanceof Error ? `${a.message}\n${a.stack || ''}` : String(a)))
        .join(' ')
        .slice(0, 800)
    )
    originalError(...args)
  }
}

export function setDebugEnabled(value) {
  debugEnabled.value = value
  try {
    localStorage.setItem(KEY, value ? '1' : '0')
  } catch {
  }
  if (value) {
    install()
    push('debug', 'debug mode enabled')
  }
}

export function debugCopyText() {
  return debugEntries.value.join('\n----------------------------------------------------------------------\n')
}

export async function debugCopyToClipboard() {
  const text = debugCopyText()
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

export function debugClear() {
  debugEntries.value = []
}

if (debugEnabled.value) {
  install()
}
