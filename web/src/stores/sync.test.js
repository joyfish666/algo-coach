import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = {
  startSync: vi.fn(),
  getSyncProgress: vi.fn(),
}

vi.mock('../api', () => ({
  api: new Proxy({}, {
    get: (_t, prop) => apiMocks[prop] ?? vi.fn(),
  }),
}))

import { useSyncStore } from './sync'
import { useToastStore } from './toast'

describe('sync store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    apiMocks.startSync.mockReset()
    apiMocks.getSyncProgress.mockReset()
  })

  afterEach(() => {
    useSyncStore()?.stopPolling?.()
    vi.useRealTimers()
  })

  const flushPoll = async () => {
    await Promise.resolve()
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(0)
  }

  it('running -> done announces success once the engine reports a real run', async () => {
    apiMocks.startSync.mockResolvedValue({ started: true })
    apiMocks.getSyncProgress
      .mockResolvedValueOnce({ running: true, fetched: 10, total: 44 })
      .mockResolvedValueOnce({
        running: false,
        fetched: 44,
        total: 44,
        started_at: '2026-08-24T00:00:00+00:00',
        finished_at: '2026-08-24T00:02:00+00:00',
      })
    const sync = useSyncStore()
    const toast = useToastStore()

    await sync.start()
    await flushPoll()
    expect(sync.phase).toBe('running')

    await vi.advanceTimersByTimeAsync(1000)
    await flushPoll()
    expect(sync.phase).toBe('done')
    expect(toast.items.some((item) => item.kind === 'success')).toBe(true)
  })

  it('engine error surfaces as a sticky toast with the reason', async () => {
    apiMocks.startSync.mockResolvedValue({ started: true })
    apiMocks.getSyncProgress.mockResolvedValue({
      running: false,
      fetched: 3,
      total: null,
      started_at: '2026-08-24T00:00:00+00:00',
      finished_at: '2026-08-24T00:01:00+00:00',
      error: 'site exploded',
    })
    const sync = useSyncStore()
    const toast = useToastStore()

    await sync.start()
    await flushPoll()
    expect(sync.phase).toBe('failed')
    const item = toast.items[0]
    expect(item.kind).toBe('error')
    expect(item.text).toContain('site exploded')
  })

  it('a fresh engine snapshot after a backend restart is NOT reported as success', async () => {
    // regression: an engine that never ran (both timestamps absent) used to
    // collapse into "done", faking a completion for a run that was swallowed
    apiMocks.startSync.mockResolvedValue({ started: true })
    apiMocks.getSyncProgress
      .mockResolvedValueOnce({ running: true, fetched: 5, total: null })
      .mockResolvedValue({ running: false, fetched: 0, total: null })
    const sync = useSyncStore()
    const toast = useToastStore()

    await sync.start()
    await flushPoll()
    expect(sync.phase).toBe('running')

    await vi.advanceTimersByTimeAsync(1000)
    await flushPoll()
    expect(sync.phase).toBe('lost')
    expect(toast.items.some((item) => item.kind === 'success')).toBe(false)
  })

  it('gives up after repeated progress failures instead of spinning forever', async () => {
    apiMocks.startSync.mockResolvedValue({ started: true })
    apiMocks.getSyncProgress.mockRejectedValue(new Error('down'))
    const sync = useSyncStore()

    await sync.start()
    for (let i = 0; i < 5; i += 1) {
      await flushPoll()
      if (i < 4) await vi.advanceTimersByTimeAsync(1000)
    }
    expect(sync.pollFailures).toBe(5)
    expect(sync.phase).toBe('lost')
  })

  it('adoptFromStatus re-attaches to an in-flight backend sync', async () => {
    apiMocks.getSyncProgress.mockResolvedValue({ running: true, fetched: 7, total: 44 })
    const sync = useSyncStore()
    sync.adoptFromStatus({ running: true, fetched: 7, total: 44 })
    await flushPoll()
    expect(sync.phase).toBe('running')
    expect(sync.fetched).toBeGreaterThanOrEqual(7)

    sync.adoptFromStatus({ running: true }) // no double adoption
    sync.stopPolling()
  })

  it('start adopts a 409 (another surface already started the engine)', async () => {
    const conflict = new Error('in progress')
    conflict.status = 409
    apiMocks.startSync.mockRejectedValue(conflict)
    apiMocks.getSyncProgress.mockResolvedValue({ running: false, fetched: 0, total: 0, started_at: 'x' })
    const sync = useSyncStore()

    await sync.start()
    await flushPoll()
    expect(sync.phase).toBe('done')
    expect(apiMocks.getSyncProgress).toHaveBeenCalled()
  })
})
