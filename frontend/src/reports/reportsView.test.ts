/** Whose trades the Reports tab asks the journal for (ADR 069 decision 6): the venue and the All / You / Bots pick. */
import { describe, expect, it } from 'vitest';
import { curveHeights } from './DrawdownPanel';
import { botCounts, countSplit, journalViewQuery, pnlSplit, readsBooks, splitWords } from './reportsView';
import { fmtPnlShort } from './format';

describe('journalViewQuery', () => {
  it('asks for nothing new on Live and Sim', () => {
    expect(journalViewQuery('live', { book: 'bots', bot: 'claude' })).toBe('');
    expect(journalViewQuery('sim', { book: 'you', bot: null })).toBe('');
    expect(journalViewQuery(undefined, undefined)).toBe('');
    expect(readsBooks('paper')).toBe(true);
    expect(readsBooks('live')).toBe(false);
  });

  it('names Paper and the pick', () => {
    expect(journalViewQuery('paper', { book: 'all', bot: null })).toBe('venue=paper');
    expect(journalViewQuery('paper', { book: 'you', bot: null })).toBe('venue=paper&owner=you');
    expect(journalViewQuery('paper', { book: 'bots', bot: null })).toBe('venue=paper&owner=bots');
    expect(journalViewQuery('paper', { book: 'bots', bot: 'live_trader' })).toBe('venue=paper&owner=bots&bot=live_trader');
  });
});

describe('botCounts', () => {
  it('counts each bot and every bot together, never your trades', () => {
    expect(botCounts([
      { owner: 'you', bot: null, trade_count: 119 },
      { owner: 'bots', bot: 'live_trader', trade_count: 233 },
      { owner: 'bots', bot: 'claude', trade_count: 6 },
    ])).toEqual({ all: 239, byBot: { live_trader: 233, claude: 6 } });
    expect(botCounts(undefined)).toBeNull();
  });
});

describe('the split beside a total', () => {
  const split = { you: { pnl: -295, trade_count: 12 }, bots: { pnl: 0, trade_count: 0 } };

  it('draws a book with no trade there as a dash', () => {
    expect(pnlSplit(split, fmtPnlShort)).toEqual({ you: { text: '-$295', value: -295 }, bots: null });
    expect(countSplit(split)).toEqual({ you: { text: '12', value: null }, bots: null });
    expect(splitWords(pnlSplit(split, fmtPnlShort))).toBe("yours -$295, the bots' —");
    expect(pnlSplit(undefined, fmtPnlShort)).toBeNull();
  });
});

describe('curveHeights', () => {
  it('draws each bar between the lowest running P&L and the highest', () => {
    expect(curveHeights([-100, 0, 100])).toEqual([3, 50, 100]);
    expect(curveHeights([-300, -200])).toEqual([3, 100]);     // a running loss is not one short bar
    expect(curveHeights([])).toEqual([]);
  });
});
