import { describe, expect, it } from 'vitest'

import { collectTags, filterProblems, paginate, pickRandom } from './problems'

const rows = [
  {
    slug: 'two-sum',
    frontend_id: '1',
    title_cn: '两数之和',
    title_en: 'Two Sum',
    difficulty: 'easy',
    tags: [
      { slug: 'array', name_zh: '数组', name_en: 'Array' },
      { slug: 'hash-table', name_zh: '哈希表', name_en: 'Hash Table' },
    ],
    practice_status: 'accepted',
  },
  {
    slug: 'shu-zu-zhong-zhong-fu-de-shu-zi-lcof',
    frontend_id: '剑指 Offer 03',
    title_cn: '数组中重复的数字',
    title_en: 'Shu Zu LCOF',
    difficulty: 'medium',
    tags: [{ slug: 'array', name_zh: '数组', name_en: 'Array' }],
    practice_status: 'wrong_answer',
  },
  {
    slug: 'add-two-num',
    frontend_id: '2',
    title_cn: '两数相加',
    title_en: 'Add Two Numbers',
    difficulty: 'medium',
    tags: [],
  },
]

describe('filterProblems', () => {
  it('filters by difficulty', () => {
    expect(filterProblems(rows, { difficulty: 'medium' })).toHaveLength(2)
  })

  it('filters by tag slug across rows', () => {
    const result = filterProblems(rows, { tagSlug: 'array' })
    expect(result.map((r) => r.slug)).toEqual(['two-sum', 'shu-zu-zhong-zhong-fu-de-shu-zi-lcof'])
  })

  it('matches non-numeric frontend id and chinese title by keyword', () => {
    expect(filterProblems(rows, { keyword: '剑指' })).toHaveLength(1)
    expect(filterProblems(rows, { keyword: 'two sum' })).toHaveLength(1)
    expect(filterProblems(rows, { keyword: '两数' })).toHaveLength(2)
    expect(filterProblems(rows, { keyword: 'LCOF' })).toHaveLength(1)
  })

  it('combines filters and ignores empty state', () => {
    expect(filterProblems(rows, {})).toHaveLength(3)
    expect(filterProblems(rows, { keyword: 'add', difficulty: 'medium' })).toHaveLength(1)
    expect(filterProblems(rows, { keyword: 'add', difficulty: 'easy' })).toHaveLength(0)
  })

  it('filters by practice status buckets', () => {
    expect(filterProblems(rows, { status: 'solved' }).map((r) => r.slug)).toEqual(['two-sum'])
    expect(filterProblems(rows, { status: 'attempted' }).map((r) => r.slug)).toEqual([
      'shu-zu-zhong-zhong-fu-de-shu-zi-lcof',
    ])
    // never-practiced rows only; attempted-but-unsolved is not "todo"
    expect(filterProblems(rows, { status: 'todo' }).map((r) => r.slug)).toEqual(['add-two-num'])
    expect(filterProblems(rows, { status: 'favorite' })).toHaveLength(0)
  })

  it('favorite filter matches only starred rows', () => {
    const starred = [{ slug: 'a', favorite: true }, { slug: 'b' }]
    expect(filterProblems(starred, { status: 'favorite' }).map((r) => r.slug)).toEqual(['a'])
  })
})

describe('pickRandom', () => {
  it('returns an element of the list', () => {
    for (let i = 0; i < 20; i += 1) {
      expect(rows).toContain(pickRandom(rows))
    }
  })

  it('handles empty input', () => {
    expect(pickRandom([])).toBeNull()
    expect(pickRandom(null)).toBeNull()
  })
})

describe('paginate', () => {
  const many = Array.from({ length: 130 }, (_, i) => ({ id: i }))

  it('slices pages and clamps out-of-range page numbers', () => {
    const pageOne = paginate(many, 1, 50)
    expect(pageOne).toMatchObject({ pages: 3, current: 1, total: 130 })
    expect(pageOne.rows[0].id).toBe(0)

    expect(paginate(many, 99, 50).current).toBe(3)
    expect(paginate(many, 0, 50).current).toBe(1)
    expect(paginate(many, 3, 50)).toMatchObject({ current: 3, total: 130 })
  })

  it('handles empty input', () => {
    expect(paginate([], 1, 50)).toMatchObject({ pages: 1, current: 1, rows: [] })
  })
})

describe('collectTags', () => {
  it('merges counts and sorts by frequency then slug', () => {
    const tags = collectTags(rows)
    expect(tags[0]).toMatchObject({ slug: 'array', count: 2 })
    expect(tags.map((t) => t.slug)).toEqual(['array', 'hash-table'])
  })

  it('returns empty list for tagless rows', () => {
    expect(collectTags([{ tags: [] }, {}])).toEqual([])
  })
})
