/**
 * Whose trades the Reports tab asks the journal for (ADR 072): the venue and the All / You / Claude / The brain /
 * Earlier bots pick, the switch's counts, and the four books beside each total.
 */
import { describe, expect, it } from 'vitest';
import { curveHeights } from './DrawdownPanel';
import { reportsRPaperStops } from './booksConstants';
import {
  botCounts, countSplit, figureSplit, journalViewQuery, pnlSplit, readsBooks, splitWords, tradedBooks,
} from './reportsView';
import { fmtPnlShort } from './format';

describe('journalViewQuery', () => {
  it('asks for nothing new on Live and Sim', () => {
    expect(journalViewQuery('live', { book: 'earlier_bots', bot: 'live_trader' })).toBe('');
    expect(journalViewQuery('sim', { book: 'claude', bot: null })).toBe('');
    expect(journalViewQuery(undefined, undefined)).toBe('');
    expect(readsBooks('paper')).toBe(true);
    expect(readsBooks('sim')).toBe(false);
    expect(readsBooks('live')).toBe(false);
  });

  it('names Paper and the pick, each book by its owner', () => {
    expect(journalViewQuery('paper', { book: 'all', bot: null })).toBe('venue=paper');
    expect(journalViewQuery('paper', { book: 'you', bot: null })).toBe('venue=paper&owner=you');
    expect(journalViewQuery('paper', { book: 'claude', bot: null })).toBe('venue=paper&owner=claude');
    expect(journalViewQuery('paper', { book: 'brain', bot: null })).toBe('venue=paper&owner=brain');
    expect(journalViewQuery('paper', { book: 'earlier_bots', bot: null })).toBe('venue=paper&owner=earlier_bots');
  });

  it('sends bot only with Earlier bots', () => {
    expect(journalViewQuery('paper', { book: 'earlier_bots', bot: 'live_trader' }))
      .toBe('venue=paper&owner=earlier_bots&bot=live_trader');
    expect(journalViewQuery('paper', { book: 'claude', bot: 'live_trader' })).toBe('venue=paper&owner=claude');
    expect(journalViewQuery('paper', { book: 'all', bot: 'live_trader' })).toBe('venue=paper');
  });
});

describe('botCounts', () => {
  it("counts each book's closed trades, a book with none at 0, and each earlier bot inside Earlier bots", () => {
    expect(botCounts([
      { owner: 'you', bot: null, trade_count: 127 },
      { owner: 'claude', bot: null, trade_count: 17 },
      { owner: 'earlier_bots', bot: 'live_trader', trade_count: 233 },
      { owner: 'earlier_bots', bot: 'bot', trade_count: 40 },
    ])).toEqual({
      all: 273,
      byBot: { live_trader: 233, bot: 40 },
      books: { you: 127, claude: 17, brain: 0, earlier_bots: 273 },
    });
    expect(botCounts([])).toEqual({ all: 0, byBot: {}, books: { you: 0, claude: 0, brain: 0, earlier_bots: 0 } });
    expect(botCounts(undefined)).toBeNull();
  });
});

describe('the split beside a total', () => {
  const split = {
    you: { pnl: -295, trade_count: 12 },
    claude: { pnl: 40.5, trade_count: 3 },
    brain: { pnl: 0, trade_count: 0 },
    earlier_bots: { pnl: -871.85, trade_count: 75 },
  };

  it('lists all four books, a book with no trade at its $0', () => {
    expect(pnlSplit(split, fmtPnlShort)).toEqual({
      you: { text: '-$295', value: -295 },
      claude: { text: '$40.50', value: 40.5 },
      brain: { text: '$0', value: 0 },
      earlier_bots: { text: '-$872', value: -871.85 },
    });
    expect(countSplit(split)).toEqual({
      you: { text: '12', value: null }, claude: { text: '3', value: null },
      brain: { text: '0', value: null }, earlier_bots: { text: '75', value: null },
    });
    expect(pnlSplit(undefined, fmtPnlShort)).toBeNull();
  });

  it('keeps only the books that traded a day, in order', () => {
    expect(tradedBooks(split)).toEqual(['you', 'claude', 'earlier_bots']);
    expect(tradedBooks(undefined)).toEqual([]);
  });

  it('says the split in words, all four or the ones given', () => {
    const figures = pnlSplit(split, fmtPnlShort);
    expect(splitWords(figures)).toBe('You -$295, Claude $40.50, The brain $0, Earlier bots -$872');
    expect(splitWords(figures, ['claude'])).toBe('Claude $40.50');
    expect(splitWords(null)).toBe('');
  });

  it('draws a book with no figure as null (a dash)', () => {
    const r = figureSplit(split, (b) => (b.trade_count > 0 ? { text: String(b.trade_count), value: null } : null));
    expect(r?.brain).toBeNull();
    expect(r?.you).toEqual({ text: '12', value: null });
  });
});

describe('reportsRPaperStops', () => {
  it("names each book that traded, mid-sentence", () => {
    expect(reportsRPaperStops([
      { owner: 'you', skipped: 2, n: 2 },
      { owner: 'claude', skipped: 0, n: 1 },
      { owner: 'brain', skipped: 0, n: 0 },
      { owner: 'earlier_bots', skipped: 4, n: 9 },
    ])).toBe("A Paper trade's stop is the stop order sent with its entry: 2 of your 2, 0 of Claude's 1 and 4 of the earlier bots' 9 sent none.");
    expect(reportsRPaperStops([{ owner: 'brain', skipped: 1, n: 3 }]))
      .toBe("A Paper trade's stop is the stop order sent with its entry: 1 of the brain's 3 sent none.");
    expect(reportsRPaperStops([])).toBe("A Paper trade's stop is the stop order sent with its entry.");
  });
});

describe('curveHeights', () => {
  it('draws each bar between the lowest running P&L and the highest', () => {
    expect(curveHeights([-100, 0, 100])).toEqual([3, 50, 100]);
    expect(curveHeights([-300, -200])).toEqual([3, 100]);     // a running loss is not one short bar
    expect(curveHeights([])).toEqual([]);
  });
});
