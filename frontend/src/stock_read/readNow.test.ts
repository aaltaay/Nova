/** The read a Trader tab draws on a Sim replay is the replay's, and never one from after the playhead (ADR 052). */
import { describe, expect, it } from 'vitest';
import { normalizeStockRead } from './normalize';
import { readNowOf } from './StockReadContext';
import { apusReadWire } from './stockReadFixtures';
import type { StockRead } from './types';

const READ = normalizeStockRead(apusReadWire) as StockRead;

describe('the read the charts draw', () => {
  const at = 1_790_947_000;
  const replayRead = { ...READ, replay: true, generated_at: at };

  it('is the live read off a replay, and never a replay read there', () => {
    expect(readNowOf(READ, false, null)).toBe(READ);
    expect(readNowOf(replayRead, false, null)).toBeNull();
  });

  it('on a replay is the replay read at or before the playhead, never a live one', () => {
    expect(readNowOf(replayRead, true, at)).toBe(replayRead);
    expect(readNowOf(replayRead, true, at + 30)).toBe(replayRead);       // played on: the next read comes
    expect(readNowOf(replayRead, true, at - 20)).toBeNull();             // scrubbed back: never what came later
    expect(readNowOf(READ, true, at)).toBeNull();                        // the edge's live read
    expect(readNowOf(replayRead, true, null)).toBe(replayRead);          // the clock not read yet
  });
});
