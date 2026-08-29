export function filterProblems(
  rows,
  { keyword = '', difficulty = '', tagSlug = '', status = '' } = {}
) {
  const kw = keyword.trim().toLowerCase()
  return (rows || []).filter((row) => {
    if (difficulty && row.difficulty !== difficulty) return false
    if (tagSlug && !(row.tags || []).some((tag) => tag.slug === tagSlug)) return false
    if (status) {
      const solved = row.practice_status === 'accepted'
      const attempted = Boolean(row.practice_status) && !solved
      if (status === 'solved' && !solved) return false
      if (status === 'attempted' && !attempted) return false
      // "todo" means never practiced; "favorite" is the starred index
      if (status === 'todo' && row.practice_status) return false
      if (status === 'favorite' && !row.favorite) return false
    }
    if (!kw) return true
    return [row.frontend_id, row.title_cn, row.title_en, row.slug].some((field) =>
      String(field || '').toLowerCase().includes(kw)
    )
  })
}

export function pickRandom(rows) {
  const list = rows || []
  if (!list.length) return null
  return list[Math.floor(Math.random() * list.length)]
}

export function paginate(rows, page, size) {
  const total = rows.length
  const pages = Math.max(1, Math.ceil(total / size))
  const current = Math.min(Math.max(1, page), pages)
  return {
    rows: rows.slice((current - 1) * size, current * size),
    pages,
    current,
    total,
  }
}

function compareById(a, b) {
  const fa = String(a.frontend_id || '')
  const fb = String(b.frontend_id || '')
  if (fa && fb && /^\d+$/.test(fa) && /^\d+$/.test(fb)) {
    return Number(fa) - Number(fb)
  }
  return fa.localeCompare(fb)
}

export function sortByMode(rows, mode) {
  const list = [...(rows || [])]
  if (mode === 'recent') {
    return list.sort((a, b) => {
      const ta = a.last_practice_at || ''
      const tb = b.last_practice_at || ''
      if (ta !== tb) return ta < tb ? 1 : -1
      return compareById(a, b)
    })
  }
  return list.sort(compareById)
}

export function collectTags(rows) {
  const bySlug = new Map()
  for (const row of rows || []) {
    for (const tag of row.tags || []) {
      if (!tag.slug) continue
      const existing = bySlug.get(tag.slug)
      if (existing) {
        existing.count += 1
      } else {
        bySlug.set(tag.slug, {
          slug: tag.slug,
          name_zh: tag.name_zh || tag.name_en,
          name_en: tag.name_en,
          count: 1,
        })
      }
    }
  }
  return [...bySlug.values()].sort(
    (a, b) => b.count - a.count || a.slug.localeCompare(b.slug)
  )
}
