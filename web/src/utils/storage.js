/**
 * Every localStorage key the app uses, plus safe read/write helpers.
 *
 * A key registry documents the storage contract in one place: lang, theme,
 * debug, density, workbench-split and panel-pos are preferences that SURVIVE
 * "erase all local data" (they are UI state, not practice data); the
 * algocoach-snapshot:* keys are code drafts and are purged by
 * purgeAllSnapshots() as part of the erase flow.
 */
export const STORAGE_KEYS = Object.freeze({
  lang: 'algocoach-lang',
  theme: 'algocoach-theme',
  debug: 'algocoach-debug',
  density: 'algocoach-density',
  workbenchSplit: 'algocoach-workbench-split',
  // one shared position for both floating panels (AI coach, notes): they are
  // mutually exclusive and open at the same spot. A dragged AI panel used to
  // persist under 'algocoach-ai-pos'; useFloatingPanel reads that as a legacy
  // fallback.
  panelPos: 'algocoach-panel-pos',
  snapshotPrefix: 'algocoach-snapshot:',
  snapshotIndex: 'algocoach-snapshot-index',
})

export function readStorage(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeStorage(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* storage unavailable or quota exceeded: drop silently */
  }
}

export function readJsonStorage(key) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function writeJsonStorage(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage unavailable or quota exceeded: drop silently */
  }
}
