import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { readJsonStorage, writeJsonStorage } from './storage'

// The workbench's floating sub-panels (AI coach, notes) share one screen
// corner: opening one closes the other, so the two can never stack up
// invisibly on top of each other.
export const activeFloatingPanel = ref(null)

/**
 * Shared mechanics for the floating sub-panels: open state, persisted
 * draggable position, Escape-to-close, viewport re-clamping and the
 * open-one-close-the-other rule. The panel's content stays in its own
 * component; this only owns the window chrome behavior.
 */
export function useFloatingPanel({ id, posKey }) {
  const open = ref(false)
  const panelEl = ref(null)

  function readPos() {
    const raw = readJsonStorage(posKey)
    if (raw && typeof raw.x === 'number' && typeof raw.y === 'number') return raw
    // one shared position since the panels merged; adopt a pre-merge dragged
    // AI-panel spot so a stored position survives the upgrade
    const legacy = readJsonStorage('algocoach-ai-pos')
    if (legacy && typeof legacy.x === 'number' && typeof legacy.y === 'number') return legacy
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
    if (pos.value) writeJsonStorage(posKey, pos.value)
  }

  function toggle() {
    open.value = !open.value
    if (open.value) activeFloatingPanel.value = id
  }

  watch(open, (value) => {
    if (value) {
      reclampToViewport()
      window.addEventListener('keydown', onGlobalKeydown)
    } else {
      window.removeEventListener('keydown', onGlobalKeydown)
    }
  })

  watch(activeFloatingPanel, (active) => {
    if (open.value && active !== id) open.value = false
  })

  onMounted(() => {
    window.addEventListener('resize', reclampToViewport)
  })

  onBeforeUnmount(() => {
    if (dragOffset) endDrag()
    window.removeEventListener('resize', reclampToViewport)
    window.removeEventListener('keydown', onGlobalKeydown)
  })

  return { open, pos, panelEl, toggle, startDrag }
}
