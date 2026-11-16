/**
 * @vitest-environment jsdom
 *
 * A pane's wait for a lane (ADR 071), alone: it never asks by itself, asks with `front=1` when brought to the front
 * or clicked, with `front=0` when a lane comes to its stock, and every waiting pane shares one lanes poll.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LANE_WAIT_POLL_MS } from '../constantGroups/market_ui';
import { bringLane, LaneWait, laneWatchersForTests, resetLaneWatchForTests } from './laneWait';

const FRAME = { type: 'lane', symbol: 'ABC', message: 'Your Level 2 moved to TGHL.', lane: { you: 'TGHL', claude: null, bots: null } };
const empty = { symbol: null, since: null, depth: false, tape: false, recording: false, error: null };

function lanesAnswer(you: string | null, bots: string | null = null) {
  return {
    ok: true, status: 200,
    json: async () => ({ schema_version: 1, you: { ...empty, symbol: you }, claude: empty,
      bots: { ...empty, symbol: bots, setup: null, why: null, waiting: [] }, recording_error: null }),
  };
}

describe('LaneWait', () => {
  let inFront = false;
  let fetchMock: ReturnType<typeof vi.fn>;
  const asked: boolean[] = [];
  const changed = vi.fn();
  const make = (symbol = 'ABC') => new LaneWait(symbol, 'Level 2', {
    inFront: () => inFront, reconnect: (front) => asked.push(front), changed,
  });

  beforeEach(() => {
    inFront = false;
    asked.length = 0;
    changed.mockReset();
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    vi.useFakeTimers();
  });

  afterEach(() => {
    resetLaneWatchForTests();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('says where your lane is, in words with and without how to bring it', () => {
    const w = make();
    w.wait(FRAME);
    expect(w.waiting).toEqual({
      you: 'TGHL',
      text: 'Your Level 2 is on TGHL — click here or bring this tab to the front to have it on ABC',
      plain: 'Your Level 2 is on TGHL, not ABC',
    });
    const none = make('XYZ');
    none.wait({ ...FRAME, lane: { you: null } });
    expect(none.waiting?.plain).toBe('No lane is on XYZ');
    w.dispose();
    none.dispose();
  });

  it('closed while waiting, it takes over from the backoff and never asks by itself, even in front', async () => {
    inFront = true;
    const w = make();
    w.wait(FRAME);
    expect(w.closed()).toBe(true);
    fetchMock.mockResolvedValue(lanesAnswer('TGHL'));
    await vi.advanceTimersByTimeAsync(10 * LANE_WAIT_POLL_MS);
    expect(asked).toEqual([]);
    w.dispose();
  });

  it('brought to the front or clicked, it asks with front=1; a lane on its stock, with front=0', async () => {
    const w = make();
    w.wait(FRAME);
    w.closed();
    w.wake();                                    // not in front: nothing
    expect(asked).toEqual([]);
    inFront = true;
    w.wake();
    expect(asked).toEqual([true]);
    w.answered();
    expect(w.waiting).toBeNull();

    const c = make('DEF');
    c.wait(FRAME);
    c.closed();
    bringLane('def');
    expect(asked).toEqual([true, true]);

    const p = make('GHI');
    p.wait(FRAME);
    p.closed();
    fetchMock.mockResolvedValue(lanesAnswer('TGHL', 'GHI'));
    await vi.advanceTimersByTimeAsync(LANE_WAIT_POLL_MS);
    expect(asked).toEqual([true, true, false]);
    [w, c, p].forEach(x => x.dispose());
  });

  it('every waiting pane shares one poll, which stops when none waits', async () => {
    const a = make('AAA');
    const b = make('BBB');
    a.wait(FRAME);
    b.wait(FRAME);
    a.closed();
    b.closed();
    expect(laneWatchersForTests()).toBe(2);
    fetchMock.mockResolvedValue(lanesAnswer('RUNR'));
    await vi.advanceTimersByTimeAsync(LANE_WAIT_POLL_MS);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(a.waiting?.you).toBe('RUNR');         // your lane moved: the words follow
    expect(changed).toHaveBeenCalled();
    a.dispose();
    b.dispose();
    expect(laneWatchersForTests()).toBe(0);
    await vi.advanceTimersByTimeAsync(3 * LANE_WAIT_POLL_MS);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('an ask that closes unanswered hands back to the backoff', () => {
    inFront = true;
    const w = make();
    w.wait(FRAME);
    w.closed();
    w.wake();
    expect(w.closed()).toBe(false);
    expect(w.waiting).toBeNull();
    w.dispose();
  });
});
