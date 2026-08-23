const PREFIX = 'algocoach-snapshot:'
const INDEX_KEY = 'algocoach-snapshot-index'
const MAX_SNAPSHOTS = 20

function snapshotKey(qid, lang) {
  return `${PREFIX}${qid}::${lang}`
}

export function saveSnapshot(qid, lang, content) {
  const key = snapshotKey(qid, lang)
  const entry = { k: key, t: Date.now() }
  let index = []
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
