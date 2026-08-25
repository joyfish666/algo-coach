const PREFIX = 'algocoach-snapshot:'
const INDEX_KEY = 'algocoach-snapshot-index'
const MAX_SNAPSHOTS = 20

function snapshotKey(qid, lang) {
  return `${PREFIX}${qid}::${lang}`
}

export function saveSnapshot(qid, lang, content) {
  const key = snapshotKey(qid, lang)
  const entry = { k: key, t: Date.now() }
  let index
  try {
    index = JSON.parse(localStorage.getItem(INDEX_KEY) || '[]')
  } catch {
    index = []
  }
  index = index.filter((item) => item.k !== key)
  index.unshift(entry)
  while (index.length > MAX_SNAPSHOTS) {
    const evicted = index.pop()
    if (evicted && evicted.k !== key) {
      try {
        localStorage.removeItem(evicted.k)
      } catch {
      }
    }
  }
  try {
    localStorage.setItem(key, JSON.stringify({ c: content, t: entry.t }))
    localStorage.setItem(INDEX_KEY, JSON.stringify(index))
  } catch {
    /* quota exceeded: drop silently */
  }
}

export function loadSnapshot(qid, lang) {
  try {
    const raw = localStorage.getItem(snapshotKey(qid, lang))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed.c !== 'string') return null
    return parsed
  } catch {
    return null
  }
}

export function snapshotNewerThan(snapshot, epochSeconds) {
  if (!snapshot || !snapshot.t) return false
  return snapshot.t > (epochSeconds || 0) * 1000
}

export function purgeAllSnapshots() {
  // part of "erase all local data": drafts live in the browser, not in the
  // backend data dir, so a server-side wipe alone let pre-erase code resurface
  // via the restore bar (solution_mtime resets to 0, making every snapshot
  // look "newer")
  try {
    const stale = []
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i)
      if (key && key.startsWith(PREFIX)) stale.push(key)
    }
    stale.forEach((key) => localStorage.removeItem(key))
    localStorage.removeItem(INDEX_KEY)
  } catch {
    /* storage unavailable: nothing to purge */
  }
}
