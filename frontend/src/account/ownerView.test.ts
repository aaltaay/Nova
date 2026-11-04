import { describe, expect, it } from 'vitest';
import type { HistoryFill, PracticeHistory } from './accountHistoryTypes';
import { positionsByOwner, positionsBySymbol } from './accountPositions';
import { ALL_VIEW, botsOf, daySplits, monthSplit, shows, viewHistory, whoName } from './ownerView';

const part = (owner: 'you' | 'bots', bot: string | null, realized: number, qty = 10) =>
  ({ owner, bot, qty, closes: true, realized, commission: 1, fees: 0 });

function fill(ts: number, parts: ReturnType<typeof part>[], owner: 'you' | 'bots' | null = parts[0].owner): HistoryFill {
  return {
    ts, order_id: ts, symbol: 'ABC', side: 'SELL', qty: parts.reduce((s, p) => s + p.qty, 0), price: 11,
    source: owner === 'you' ? 'manual' : 'bot', bot_id: null, commission: parts.length, fees: 0,
    realized: parts.reduce((s, p) => s + p.realized, 0), fill_estimated: true, fill_basis: 'test',
    owner, bot: parts[0].bot, parts,
  };
}

const history = (): PracticeHistory => ({
  venue: 'paper', account_id: 'NOVA-PAPER', range: '1M', range_start: null, schema_version: 2, starting_cash: 100_000,
  ledger_opened_at: null,
  equity: [{ ts: 2, net_liquidation: 100_050, cash: 100_050, realized: 50, unrealized: 0, you_pnl: 98, bots_pnl: -48,
             you_realized: 98, bots_realized: -48, by_bot: { live_trader: -48 }, by_bot_realized: { live_trader: -48 } }],
  fills: [fill(1, [part('you', null, 98)]), fill(2, [part('bots', 'live_trader', -48)]),
          fill(3, [part('you', null, 5, 4), part('bots', 'claude', 2, 6)], null)],
  by_source: [],
  by_owner: [{ owner: 'you', bot: null, realized: 103, fills: 2, commissions: 2, fees: 0 },
             { owner: 'bots', bot: 'live_trader', realized: -48, fills: 1, commissions: 1, fees: 0 },
             { owner: 'bots', bot: 'claude', realized: 2, fills: 1, commissions: 1, fees: 0 }],
  daily: [{ date: '2026-11-03', realized: 57, commissions: 4, fees: 0, fills: 3, archived: false,
            you: { realized: 103, fills: 2, commissions: 2, fees: 0 }, bots: { realized: -46, fills: 2, commissions: 2, fees: 0 },
            by_bot: { live_trader: { realized: -48, fills: 1, commissions: 1, fees: 0 },
                      claude: { realized: 2, fills: 1, commissions: 1, fees: 0 } } }],
  archives: [],
  components: { realized: 57, unrealized: 0, commissions: 4, sec_finra_fees: 0, bot_realized: -46 },
  warnings: [],
});

describe('whose trades the Account page shows (ADR 069)', () => {
  it('All passes the history through unchanged', () => {
    const h = history();
    expect(viewHistory(h, ALL_VIEW)).toBe(h);
  });

  it('You keeps your parts of each fill, your days and your running P&L', () => {
    const you = viewHistory(history(), { book: 'you', bot: null })!;
    expect(you.fills.map((f) => [f.ts, f.realized, f.qty])).toEqual([[1, 98, 10], [3, 5, 4]]);
    expect(you.daily.map((d) => [d.date, d.realized, d.fills])).toEqual([['2026-11-03', 103, 2]]);
    expect(you.components.realized).toBe(103);
    expect(you.equity[0]).toMatchObject({ realized: 98, unrealized: 0, net_liquidation: 100_098 });
    expect(you.by_owner?.map((r) => r.owner)).toEqual(['you']);
  });

  it('one bot is that bot alone', () => {
    const claude = viewHistory(history(), { book: 'bots', bot: 'claude' })!;
    expect(claude.fills.map((f) => f.realized)).toEqual([2]);
    expect(claude.daily[0].realized).toBe(2);
  });

  it('a history with no split (Sim) is never narrowed', () => {
    const sim = { ...history(), fills: history().fills.map(({ parts: _parts, ...f }) => f) } as PracticeHistory;
    expect(viewHistory(sim, { book: 'you', bot: null })).toBe(sim);
  });

  it('names and splits read the wire', () => {
    expect([whoName('you', null), whoName('bots', 'live_trader'), whoName(null, null)]).toEqual(['You', 'Live Trader', 'Nova']);
    expect(shows({ book: 'bots', bot: null }, 'bots', 'claude')).toBe(true);
    expect(shows({ book: 'you', bot: null }, 'bots', 'claude')).toBe(false);
    expect(botsOf(history())).toEqual(['live_trader', 'claude']);
    const splits = daySplits(history());
    expect(splits?.get('2026-11-03')).toEqual({ you: 103, bots: -46 });
    expect(monthSplit(splits, '2026-11')).toEqual({ you: 103, bots: -46 });
  });

  it('a Paper position becomes one row per holder, each at its own cost', () => {
    const rows = positionsByOwner([{ symbol: 'spcx', qty: 104, avg_cost: 140.96, mark: 141, unrealized: 4,
      by_owner: [{ owner: 'you', bot: null, qty: 100, avg_cost: 141, unrealized_pnl: 0 },
                 { owner: 'bots', bot: 'live_trader', qty: 4, avg_cost: 140, unrealized_pnl: 4 }] }]);
    expect(rows.map((r) => [r.symbol, r.owner, r.bot, r.qty, r.avgCost, r.marketValue])).toEqual([
      ['SPCX', 'you', null, 100, 141, 14_100], ['SPCX', 'bots', 'live_trader', 4, 140, 564],
    ]);
    const [one] = positionsBySymbol(rows);
    expect([one.qty, one.marketValue, one.unrealized, one.owner]).toEqual([104, 14_664, 4, undefined]);
    expect(one.avgCost).toBeCloseTo(140.96, 6);
  });
});
