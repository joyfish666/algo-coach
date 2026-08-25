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
let consolePatched = false
const originalConsoleError = console.error.bind(console)

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
}

function patchConsole() {
  if (consolePatched) return
  consolePatched = true
  console.error = (...args) => {
    push(
      'console.error',
      args
        .map((a) => (a instanceof Error ? `${a.message}\n${a.stack || ''}` : String(a)))
        .join(' ')
        .slice(0, 800)
    )
    originalConsoleError(...args)
  }
}

function unpatchConsole() {
  if (!consolePatched) return
  consolePatched = false
  console.error = originalConsoleError
}

export function setDebugEnabled(value) {
  debugEnabled.value = value
  try {
    localStorage.setItem(KEY, value ? '1' : '0')
  } catch {
  }
  if (value) {
    install()
    patchConsole()
    push('debug', 'debug mode enabled')
  } else {
    // turning the bar off must also restore console.error; a one-way hijack
    // degraded every later console.error into String()-concatenation
    unpatchConsole()
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

export function debugLog(level, text) {
  push(level, String(text).slice(0, 800))
}

if (debugEnabled.value) {
  install()
  patchConsole()
}
