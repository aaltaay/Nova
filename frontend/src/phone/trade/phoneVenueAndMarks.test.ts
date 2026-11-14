/**
 * @vitest-environment jsdom
 *
 * The phone's venue, Sim and Level 2 marks (ADR 070 amendment 2026-11-13): what the Trade screen draws on each
 * venue, what the venue menu says before a switch, the Sim strip's word, the marks on the book and the read
 * page's cards, the marks switch, and the read page's route.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { applyBookWatchFrame, type BookWatchState } from '../../ibkr/bookWatch';
import type { DepthLevel } from '../../ibkr/types';
import type { SimClockState } from '../../sim';
import { parseRoute, routeHash, tabOf } from '../phoneRoute';
import { readCards } from '../screens/BookScreen';
import { effectsFoot, simRowNote } from '../VenueMenu';
import { bannerWords, sideMarks } from './BookMarks';
import { LEVEL2_MARKS_KEY, readLevel2Marks, setLevel2Marks } from './level2MarksSwitch';
import { simStripState } from './SimStrip';
import { CAPTURE_GAP, LIVE_LOOK_ONLY, massiveNote, tradeVenueView } from './tradeVenueView';

const NOW_S = 1_790_682_311.878;
const NOW_MS = 7_000_000;

function wall(over: Record<string, unknown> = {}) {
  return {
    id: '1790682300000-XYZ-ask-3.45', kind: 'big_seller', side: 'ask', price: 3.45, state: 'holding',
    size_first: 48_200, size_now: 48_200, size_peak: 48_200, traded: 0, median_level: 2_400, multiple: 20.1,
    first_seen_ts: NOW_S - 20, seen_from_start: false, called_ts: NOW_S - 17, ended_ts: null, held_sec: 20,
    distance: 0.01, distance_pct: 0.29, distance_called: 0.01, on_approach: null, back: null, clear_sec: 40.2,
    how: null, left: null, ...over,
  };
}

function watch(over: Record<string, unknown> = {}): BookWatchState {
  const s = applyBookWatchFrame(null, {
    schema_version: 1, now: NOW_S, reset: true, seq: 0, watching: true, reason: null, window_sec: 60,
    sides: {
      bid: { pulled_shares: 0, filled_shares: 0, large_pulls: 0, hidden_shares: 0 },
      ask: { pulled_shares: 0, filled_shares: 0, large_pulls: 0, hidden_shares: 0 },
    },
    drops: [], hidden: [], big: [wall()], big_float: { shares: 2_500_000, contradicted: false },
    ...over,
  }, NOW_MS);
  if (!s) throw new Error('no state');
  return s;
}

const lvl = (price: number, size: number, side: 'bid' | 'ask', mm = 'NSDQ'): DepthLevel => ({ price, size, side, mm });
const ASKS = [lvl(3.44, 1800, 'ask'), lvl(3.45, 30_000, 'ask'), lvl(3.45, 18_200, 'ask', 'ARCA'), lvl(3.46, 2100, 'ask')];
const BIDS = [lvl(3.43, 900, 'bid'), lvl(3.42, 1200, 'bid')];

const clock = (over: Partial<SimClockState> = {}): SimClockState => ({ sim: true, ...over });

describe('what Trade draws on each venue', () => {
  it('trades Paper live, and looks at Live with a ticket that sends nothing', () => {
    expect(tradeVenueView('F', 'paper', null, false)).toEqual({ feedKey: 'live', quote: 'live', note: null, gap: false, blocked: null });
    const live = tradeVenueView('F', 'live', null, false);
    expect(live.blocked).toEqual({ why: LIVE_LOOK_ONLY, word: 'Live · look only' });
    expect(live.note).toBeNull();
  });

  it('is live at the Sim live edge, as Paper is, and trades the Sim', () => {
    expect(tradeVenueView('F', 'sim', clock({ live_edge: true, replay_source: 'capture', replay_symbol: 'K' }), true))
      .toEqual({ feedKey: 'live-edge', quote: 'live', note: null, gap: false, blocked: null });
  });

  it("follows a Session Record of this stock off the edge, with its quote, and says a gap as a gap", () => {
    const on = tradeVenueView('F', 'sim', clock({ replay_source: 'capture', replay_symbol: 'F', replay_quote: { symbol: 'F', ts: 1, covered: true, last: 3, bid: 2.9, ask: 3, bid_size: 1, ask_size: 1, prev_close: 2 } }), true);
    expect(on).toEqual({ feedKey: 'replay', quote: 'capture', note: null, gap: false, blocked: null });
    const gap = tradeVenueView('F', 'sim', clock({ replay_source: 'capture', replay_symbol: 'F', replay_quote: { symbol: 'F', ts: 1, covered: false, last: null, bid: null, ask: null, bid_size: null, ask_size: null, prev_close: null } }), true);
    expect(gap.gap).toBe(true);
    expect(CAPTURE_GAP).toContain('nothing was recorded here');
  });

  it("puts the desk's words in place of the book, and locks the ticket, for anything else on Sim", () => {
    const other = tradeVenueView('F', 'sim', clock({ replay_source: 'capture', replay_symbol: 'K' }), true);
    expect(other.note).toContain('K');
    expect(other.blocked?.why).toBe(other.note);
    expect(other.quote).toBe('empty');
    expect(tradeVenueView('F', 'sim', clock({ replay_source: 'none' }), true).blocked).not.toBeNull();
    expect(tradeVenueView('F', 'sim', null, true).blocked).not.toBeNull();
  });

  it('says a Massive-file replay of this stock is on the PC, never draws today over it', () => {
    const v = tradeVenueView('F', 'sim', clock({ replay_source: 'historical', replay_symbol: 'F' }), true);
    expect(v).toMatchObject({ quote: 'empty', note: massiveNote('F'), blocked: { why: massiveNote('F'), word: 'Sim · on the PC' } });
  });
});

describe('the venue menu, before the tap', () => {
  it("names the Sim's replay, the live edge, or that nothing is loaded", () => {
    expect(simRowNote(null)).toBe("the desk's replay");
    expect(simRowNote(clock({ live_edge: true }))).toBe('the live edge · live IBKR prices');
    expect(simRowNote(clock({ replay_source: 'capture', replay_symbol: 'plce', session_date: '2026-11-12', sim_time_et: '2026-11-12T15:31:05Z' })))
      .toMatch(/^PLCE · Nov 12 · \d\d:\d\d:\d\d$/);
    expect(simRowNote(clock({ replay_source: 'none', session_date: '2026-11-12' }))).toBe('nothing loaded · Nov 12');
  });

  it('says what the switch would cancel, or that nothing works there, and never reads a failed check as nothing', () => {
    expect(effectsFoot('paper', null)).toBeNull();
    expect(effectsFoot('paper', { venue: 'paper', lines: [], unknown: [] }))
      .toEqual({ stake: false, text: 'Nothing working on Paper. Your own orders and shares stay on Paper.' });
    expect(effectsFoot('paper', { venue: 'paper', lines: ["Cancels on Paper: the Bot's buy of F.", 'The Bot is on for Paper: switching turns it off'], unknown: [] }))
      .toEqual({ stake: true, text: "Cancels on Paper: the Bot's buy of F. The Bot is on for Paper: switching turns it off. Your own orders and shares stay on Paper." });
    expect(effectsFoot('sim', { venue: 'sim', lines: [], unknown: ['armed'] })?.text).toContain('Nova could not read: armed.');
    expect(effectsFoot('sim', 'none')).toMatchObject({ stake: true });
  });
});

describe("the Sim strip's word", () => {
  it('says the live edge, paused, a replay, or nothing loaded', () => {
    expect(simStripState(null)).toBe('reading the desk');
    expect(simStripState(clock({ live_edge: true }))).toBe('live edge');
    expect(simStripState(clock({ paused: true, replay_source: 'capture' }))).toBe('paused');
    expect(simStripState(clock({ replay_source: 'capture' }))).toBe('replay');
    expect(simStripState(clock({ replay_source: 'none' }))).toBe('nothing loaded');
  });
});

describe("the desk's marks on the phone's book", () => {
  it('frames every row of a big seller and names it over the column head, short enough for the phone', () => {
    const m = sideMarks(watch(), 'ask', ASKS, NOW_MS);
    expect([...m.big.keys()]).toEqual([1, 2]);
    expect(m.banner).not.toBeNull();
    // The float and the pace stay on the desk's banner and on the read page's card.
    expect(bannerWords(m.banner!)).toBe('Big seller 3.45 · 48.2K');
  });

  it('draws nothing with no watch, and nothing on a side with no rows', () => {
    expect(sideMarks(null, 'ask', ASKS, NOW_MS)).toMatchObject({ marks: [], banner: null });
    expect(sideMarks(watch(), 'bid', [], NOW_MS).big.size).toBe(0);
  });

  it("lists every mark as a card on the read page, big first, in the desk's own words", () => {
    const cards = readCards(watch(), BIDS, ASKS, NOW_MS);
    expect(cards[0]).toMatchObject({ kind: 'big', side: 'ask', title: 'Big seller 3.45 · 48.2K · 1.9% of float · 40 s of lit volume' });
    expect(readCards(null, BIDS, ASKS, NOW_MS)).toEqual([]);
  });
});

describe('the marks switch', () => {
  afterEach(() => setLevel2Marks(true));

  it('starts on, and remembers off on this phone', () => {
    expect(readLevel2Marks()).toBe(true);
    setLevel2Marks(false);
    expect(readLevel2Marks()).toBe(false);
    expect(localStorage.getItem(LEVEL2_MARKS_KEY)).toContain('false');
  });
});

describe("the Level 2 read page's address", () => {
  it('names the stock in the hash, and lights the Trade tab', () => {
    const route = { screen: 'book', symbol: 'PLCE' } as const;
    expect(routeHash(route)).toBe('#/book/PLCE');
    expect(parseRoute('#/book/PLCE')).toEqual(route);
    expect(parseRoute('#/book')).toEqual({ screen: 'home' });
    expect(tabOf(route)).toBe('trade');
  });
});
