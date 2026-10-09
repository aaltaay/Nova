/** The Sim board's words on a loaded replay (ADR 052): what it follows, what its tape gate reads, a rewind's catch-up. */
import { describe, expect, it } from 'vitest';
import { simBoardLine, simBoardTip } from './simBoardWords';
import type { SetupsBoard, SetupsReplay } from './types';

function board(replay: Partial<SetupsReplay>): SetupsBoard {
  return {
    source: 'sim',
    replay: { kind: 'history', date: '2026-10-02', symbol: 'AMOD', playhead: 100, at: 100, loading: false,
      error: null, note: null, ...replay },
  } as unknown as SetupsBoard;
}

describe('the Sim board on a loaded window', () => {
  it('names the replay and what its tape gate reads', () => {
    const nbbo = board({ book: 'nbbo', note: 'the tape gate reads the window\'s NBBO (Level 1): a download has no Level 2' });
    expect(simBoardLine(nbbo)).toBe('Sim eyes on AMOD 2026-10-02 · the tape gate reads the window\'s NBBO (Level 1): '
      + 'a download has no Level 2');
    expect(simBoardTip(nbbo)).toMatch(/the bot trades their go triggers/);
    expect(simBoardTip(nbbo)).toMatch(/NBBO, the best bid and ask only/);
    expect(simBoardTip(board({ book: 'none' }))).toMatch(/IBKR download has no bid or ask/);
  });

  it('says it is catching up while a rewind waits for its rebuild, never the later lanes', () => {
    expect(simBoardLine(board({ loading: true, at: 160, playhead: 100 }))).toMatch(/catching up to the playhead/);
    expect(simBoardLine(board({ loading: true, at: null }))).toMatch(/reading the replay/);
  });
});
