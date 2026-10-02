/** Tickers today's words and order (ADR 044), pure. */
import { describe, expect, it } from 'vitest';
import type { StockModeRow } from './stockModesApi';
import { allStops, daySummary, orderTickers, resultWords, sidesOf, splitReasons, stopWord } from './tickerTable';
import type { Cells, TickerRow, TickerTrigger } from './triggersApi';

const ORDER = ['bot_on', 'strategy_on', 'grade', 'setups_a_day', 'bot_window', 'hot_list', 'nova_buys', 'level2_line',
  'tape_go', 'trades_today'];
const cell = (ok: boolean | null, why = '') => ({ ok, why });
const mode = (symbol: string, m: StockModeRow['mode']) => ({ symbol, mode: m }) as StockModeRow;
const trigger = (partial: Partial<TickerTrigger> = {}): TickerTrigger => ({
  ts: 0, setup_id: null, setup_type: 'first_pullback', kind: null, nth: 1, grade: 'B', tape: 'blind', outcome: null, r: null,
  cells: {}, reasons: [], ...partial,
});
const row = (symbol: string, at: number | null, triggers: TickerTrigger[] = []): TickerRow => ({
  symbol, listed: at === null ? null : { how: 'star', at }, now: null, triggers,
});

describe('tickers today', () => {
  it('reads Buy and Sell from the stock\'s mode, You and You when it has none', () => {
    const modes = [mode('AISP', 'bot'), mode('LPA', 'auto_entry'), mode('MEDS', 'approve')];
    expect(sidesOf('AISP', modes)).toEqual(['nova', 'nova']);
    expect(sidesOf('LPA', modes)).toEqual(['nova', 'you']);
    expect(sidesOf('MEDS', modes)).toEqual(['you', 'nova']);
    expect(sidesOf('JAGU', modes)).toEqual(['you', 'you']);
  });

  it('lists the stocks Nova buys first, then by when they joined; the rest by symbol', () => {
    const { listed, unlisted } = orderTickers([row('MEDS', 10), row('AISP', 30), row('LPA', 20), row('ZZZ', null),
      row('ABC', null)], [mode('AISP', 'bot')]);
    expect(listed.map(t => t.symbol)).toEqual(['AISP', 'MEDS', 'LPA']);
    expect(unlisted.map(t => t.symbol)).toEqual(['ABC', 'ZZZ']);
  });

  it('says each red in a few words, with the trigger\'s own grade and tape', () => {
    expect(stopWord('level2_line')).toBe('BLIND: no Level 2 line');
    expect(stopWord('grade', { grade: 'C' })).toBe('grade C');
    expect(stopWord('tape_go', { tape: 'wait' })).toBe('tape WAIT');
    expect(stopWord('tape_go')).toBe('tape not GO');
  });

  it('splits a now row\'s reds into its own and the shared ones, and keeps a trigger\'s in gate order', () => {
    const cells: Cells = { bot_on: cell(false, 'the bot was off'), nova_buys: cell(false, 'Buy is You on AISP'),
      bot_window: cell(false, 'outside 07:00-10:00'), level2_line: cell(true), tape_go: cell(null) };
    const { own, shared } = splitReasons(cells, ORDER);
    expect(own.map(s => s.word)).toEqual(['Buy is You']);
    expect(shared.map(s => s.id)).toEqual(['bot_on', 'bot_window']);
    expect(allStops(cells, ORDER).map(s => s.id)).toEqual(['bot_on', 'bot_window', 'nova_buys']);
    expect(allStops(cells, ORDER)[0].why).toBe('the bot was off');
  });

  it('says a trigger\'s result and the ticker\'s day', () => {
    expect(resultWords(trigger({ outcome: 'target_first', r: 1.6 }))).toEqual({ text: 'target +1.60R', tone: 'win' });
    expect(resultWords(trigger({ outcome: 'stop_first', r: -1 }))).toEqual({ text: 'stop -1.00R', tone: 'loss' });
    expect(resultWords(trigger())).toEqual({ text: 'not scored yet', tone: 'open' });
    const day = row('AISP', 1, [trigger({ outcome: 'target_first', r: 1 }), trigger({ outcome: 'stop_first', r: -1 }),
      trigger({ outcome: 'stop_first', r: -1 })]);
    expect(daySummary(day)).toBe('3 today · 1 hit · -1.0R');
    expect(daySummary(row('X', 1))).toBe('–');
  });
});
