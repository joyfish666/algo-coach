export function filterProblems(rows, { keyword = '', difficulty = '', tagSlug = '' } = {}) {
  const kw = keyword.trim().toLowerCase()
  return (rows || []).filter((row) => {
    if (difficulty && row.difficulty !== difficulty) return false
    if (tagSlug && !(row.tags || []).some((tag) => tag.slug === tagSlug)) return false
    if (!kw) return true
    return [row.frontend_id, row.title_cn, row.title_en, row.slug].some((field) =>
      String(field || '').toLowerCase().includes(kw)
    )
  })
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
