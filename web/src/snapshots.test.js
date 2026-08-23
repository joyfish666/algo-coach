import { afterEach, describe, expect, it } from 'vitest'

import { loadSnapshot, saveSnapshot, snapshotNewerThan } from './snapshots'

function indexKeys() {
  const raw = localStorage.getItem('algocoach-snapshot-index')
  return raw ? JSON.parse(raw).map((item) => item.k) : []
}

afterEach(() => {
  localStorage.clear()
})

describe('editor snapshots', () => {
  it('round-trips content per qid+lang key', () => {
    saveSnapshot('two-sum', 'cpp', 'int main() {}')
    expect(loadSnapshot('two-sum', 'cpp')).toMatchObject({ c: 'int main() {}' })
    expect(loadSnapshot('two-sum', 'python3')).toBeNull()
  })

  it('overwrites same key without duplicating index entries', () => {
    saveSnapshot('two-sum', 'cpp', 'v1')
    saveSnapshot('two-sum', 'cpp', 'v2')
    const keys = indexKeys()
    expect(keys).toHaveLength(1)
    expect(loadSnapshot('two-sum', 'cpp').c).toBe('v2')
  })

  it('evicts the oldest entry beyond twenty keys (per qid+lang)', () => {
    for (let i = 0; i < 22; i += 1) {
      saveSnapshot(`problem-${i}`, 'cpp', `code-${i}`)
    }
    const keys = indexKeys()
    expect(keys).toHaveLength(20)
    expect(keys.some((k) => k.includes('problem-21'))).toBe(true)
    expect(keys.some((k) => k.includes('problem-1::'))).toBe(false)
    expect(loadSnapshot('problem-1', 'cpp')).toBeNull()
    expect(loadSnapshot('problem-21', 'cpp').c).toBe('code-21')
  })
})

describe('snapshotNewerThan', () => {
  it('compares snapshot milliseconds against disk epoch seconds', () => {
    const snap = { c: 'x', t: 1700000000000 }
    expect(snapshotNewerThan(snap, 1699999999)).toBe(true)
    expect(snapshotNewerThan(snap, 1700000001)).toBe(false)
    expect(snapshotNewerThan(null, 0)).toBe(false)
  })
})
