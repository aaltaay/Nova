/**
 * @vitest-environment jsdom
 */
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readWatchlistEntries, readWatchlistResponse, useWatchlist } from './useWatchlist';

const simMocks = vi.hoisted(() => ({
  replayDesk: false,
  playhead: null as number | null,
  sessionDate: null as string | null,
}));

vi.mock('../sim', () => ({
  useSimReplayDesk: () => simMocks.replayDesk,
  useSimReplayPlayhead: () => simMocks.playhead,
  simClockResource: {
    getSnapshot: () => ({ data: simMocks.sessionDate ? { session_date: simMocks.sessionDate } : null }),
  },
}));

const entry = (symbol: string) => ({
  symbol,
  composite_score: 72,
  sub_scores: { change_pct: 1, relative_volume: 1, float: 1, catalyst: 1 },
  five_pillars: { symbol, all_pass: false, pass_count: 3, total: 5, checkmark: '·', pillars: [] },
});

describe('readWatchlistEntries (QA C15)', () => {
  it('refuses a JSON array: data.entries is Array.prototype.entries, a function', () => {
    expect(typeof ([] as unknown as { entries: unknown }).entries).toBe('function');
    expect(readWatchlistEntries([])).toBeNull();
    expect(readWatchlistEntries([entry('GRML')])).toBeNull();
  });

  it('refuses bodies that carry no entry list', () => {
    expect(readWatchlistEntries(null)).toBeNull();
    expect(readWatchlistEntries('ok')).toBeNull();
    expect(readWatchlistEntries({ entries: 'GRML' })).toBeNull();
    expect(readWatchlistEntries({ note: 'x', count: 0 })).toBeNull();
  });

  it('keeps well-formed entries and drops ones a renderer would crash on', () => {
    const out = readWatchlistEntries({
      note: 'x',
      count: 4,
      entries: [entry('GRML'), { symbol: 'NOPILLARS', composite_score: 50 }, { composite_score: 1 }, entry('VXTL')],
    });
    expect(out?.map((e) => e.symbol)).toEqual(['GRML', 'VXTL']);
    expect(readWatchlistEntries({ entries: [] })).toEqual([]);
  });
});

describe('readWatchlistResponse and useWatchlist source transitions (#881)', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    simMocks.replayDesk = false;
    simMocks.playhead = null;
    simMocks.sessionDate = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.restoreAllMocks();
  });

  it('parses replay provenance and rejects malformed replay payloads', () => {
    const parsed = readWatchlistResponse({
      note: 'x',
      count: 1,
      source: 'replay',
      entries: [entry('KUST')],
      replay: {
        session_date: '2026-07-15',
        at: 1_752_578_426,
        minute_ts: 1_752_578_400,
        board_source: 'reconstructed',
        covered: true,
        absent: null,
      },
    });
    expect(parsed?.source).toBe('replay');
    expect(parsed?.replay?.session_date).toBe('2026-07-15');
    expect(parsed?.replay?.board_source).toBe('reconstructed');
    expect(readWatchlistResponse({ note: 'x', count: 0, source: 'replay', entries: [], replay: null })).toBeNull();
  });

  it('clears stale entries across live-edge / replay transitions and drops older late poll responses', async () => {
    let resolvePendingPoll: ((res: Response) => void) | null = null;
    const fetchMock = vi.fn()
      // 1. Initial live poll succeeds with TODAY.
      .mockResolvedValueOnce(new Response(JSON.stringify({
        note: 'x', count: 1, source: 'live', replay: null, entries: [entry('TODAY')],
      }), { status: 200 }))
      // 2. First replay poll at 07:20:00 hangs until after 07:20:26 resolves.
      .mockImplementationOnce(() => new Promise<Response>((r) => { resolvePendingPoll = r; }))
      // 3. Second replay poll at 07:20:26 resolves with KUST.
      .mockResolvedValueOnce(new Response(JSON.stringify({
        note: 'x', count: 1, source: 'replay', entries: [entry('KUST')],
        replay: {
          session_date: '2026-07-15', at: 1_752_578_426, minute_ts: 1_752_578_400,
          board_source: 'reconstructed', covered: true, absent: null,
        },
      }), { status: 200 }))
      // 4. Rewind poll to 07:15 ET returns REWOUND.
      .mockResolvedValueOnce(new Response(JSON.stringify({
        note: 'x', count: 1, source: 'replay', entries: [entry('REWOUND')],
        replay: {
          session_date: '2026-07-15', at: 1_752_578_100, minute_ts: 1_752_578_100,
          board_source: 'reconstructed', covered: true, absent: null,
        },
      }), { status: 200 }))
      // 5. Return to live edge returns LIVE_AGAIN.
      .mockResolvedValueOnce(new Response(JSON.stringify({
        note: 'x', count: 1, source: 'live', replay: null, entries: [entry('LIVE_AGAIN')],
      }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    let state: ReturnType<typeof useWatchlist> | null = null;
    function Probe({ tick }: { tick: number }) {
      void tick;
      state = useWatchlist(true);
      return null;
    }

    await act(async () => {
      root.render(createElement(Probe, { tick: 0 }));
    });
    expect(state?.entries.map(e => e.symbol)).toEqual(['TODAY']);
    expect(state?.replay).toBeNull();

    // Switch to replay desk at 07:20:00 ET (this poll stays pending); TODAY must be cleared immediately.
    simMocks.replayDesk = true;
    simMocks.sessionDate = '2026-07-15';
    simMocks.playhead = 1_752_578_400;
    await act(async () => {
      root.render(createElement(Probe, { tick: 1 }));
    });
    expect(state?.entries).toEqual([]);
    expect(state?.loading).toBe(true);

    // Advance playhead to 07:20:26 ET; this poll resolves with KUST.
    simMocks.playhead = 1_752_578_426;
    await act(async () => {
      root.render(createElement(Probe, { tick: 2 }));
    });
    expect(state?.entries.map(e => e.symbol)).toEqual(['KUST']);
    expect(state?.replay?.session_date).toBe('2026-07-15');

    // Now the earlier pending poll resolves late with stale data: must be dropped!
    await act(async () => {
      resolvePendingPoll?.(new Response(JSON.stringify({
        note: 'x', count: 1, source: 'live', replay: null, entries: [entry('STALE_LIVE')],
      }), { status: 200 }));
    });
    expect(state?.entries.map(e => e.symbol)).toEqual(['KUST']);
    expect(state?.replay?.session_date).toBe('2026-07-15');

    // Rewind to 07:15 ET replaces entries with REWOUND.
    simMocks.playhead = 1_752_578_100;
    await act(async () => {
      root.render(createElement(Probe, { tick: 3 }));
    });
    expect(state?.entries.map(e => e.symbol)).toEqual(['REWOUND']);
    expect(state?.replay?.minute_ts).toBe(1_752_578_100);

    // Return to live edge replaces replay entries with LIVE_AGAIN and clears replay provenance.
    simMocks.replayDesk = false;
    simMocks.sessionDate = null;
    simMocks.playhead = null;
    await act(async () => {
      root.render(createElement(Probe, { tick: 4 }));
    });
    expect(state?.entries.map(e => e.symbol)).toEqual(['LIVE_AGAIN']);
    expect(state?.replay).toBeNull();
    expect(state?.source).toBe('live');
  });
});
