import { describe, expect, it } from 'vitest';
import { normalizeBoard, normalizeCandles } from './normalize';

describe('normalizeBoard', () => {
  it('refuses an answer that is not this board', () => {
    expect(normalizeBoard(null)).toBeNull();
    expect(normalizeBoard([])).toBeNull();
    expect(normalizeBoard({ schema_version: 2 })).toBeNull();
    expect(normalizeBoard({})).toBeNull();
  });

  it('reads every missing figure as unknown, never 0', () => {
    const b = normalizeBoard({ schema_version: 1 })!;
    expect(b.enabled).toBe(true);
    expect(b.loading).toBe(false);
    expect(b.coins).toEqual([]);
    expect(b.market.total_cap_usd).toBeNull();
    expect(b.market.fear_greed).toBeNull();
    expect(b.market.btc_qqq_corr_30d).toBeNull();
    expect(b.leverage.open_interest_usd).toBeNull();
    expect(b.flows.stablecoins).toBeNull();
    expect(b.bridge.phase).toBe('overnight');
    expect(b.bridge.btc_since_close_pct).toBeNull();
    expect(b.clock.stock_next).toBeNull();
    expect(b.clock.lanes.regular).toEqual([]);
  });

  it('keeps liquidations and ETF flows stated absences whatever the wire says', () => {
    const b = normalizeBoard({
      schema_version: 1,
      leverage: { liquidations_24h: 5e8, liquidations_note: 'No free source.' },
      flows: { etf: { net_usd: 1 }, etf_note: 'No free source publishes them.' },
    })!;
    expect(b.leverage.liquidations_24h).toBeNull();
    expect(b.leverage.liquidations_note).toBe('No free source.');
    expect(b.flows.etf).toBeNull();
    expect(b.flows.etf_note).toBe('No free source publishes them.');
  });

  it('reads a coin defensively: strings and infinities are not numbers', () => {
    const b = normalizeBoard({
      schema_version: 1,
      enabled: false,
      coins: [
        { symbol: 'BTC', name: 'Bitcoin', price: '112480', change_24h_pct: Number.POSITIVE_INFINITY, spark_7d: [1, 'x', 2],
          ibkr: { listed: true, venue: 'PAXOS' }, why: { kind: 'catalyst', title: 'ETF inflows' }, chart: true },
        { name: 'no symbol' },
        { symbol: 'PEPE', ibkr: { listed: 'yes' }, why: { kind: 'rumour', title: 'x' } },
      ],
    })!;
    expect(b.enabled).toBe(false);
    expect(b.coins.map((c) => c.symbol)).toEqual(['BTC', 'PEPE']);
    const [btc, pepe] = b.coins;
    expect(btc.price).toBeNull();
    expect(btc.change_24h_pct).toBeNull();
    expect(btc.spark_7d).toEqual([1, 2]);
    expect(btc.ibkr).toEqual({ listed: true, venue: 'PAXOS' });
    expect(btc.why?.kind).toBe('catalyst');
    expect(btc.chart).toBe(true);
    expect(pepe.name).toBe('PEPE');
    expect(pepe.ibkr).toBeNull();
    expect(pepe.why).toBeNull();
    expect(pepe.news_checked).toBe(false);
  });

  it('drops rows it cannot read and keeps the rest', () => {
    const b = normalizeBoard({
      schema_version: 1,
      bridge: { phase: 'premarket', rows: [{ symbol: 'MARA', beta: 2.4, read: 'sideways' }, { beta: 1 }] },
      news: [{ published_ts: 1, symbol: 'SUI', kind: 'catalyst', title: 'Listed' }, { published_ts: 1, symbol: 'SUI', kind: 'hype', title: 'x' }],
      next: [{ at: 5, kind: 'funding', title: 'Funding' }, { at: 5, kind: 'party', title: 'x' }],
      sources: [{ id: 'coingecko', ok: 'yes' }, { id: 'binance', ok: true }],
    })!;
    expect(b.bridge.phase).toBe('premarket');
    expect(b.bridge.rows).toHaveLength(1);
    expect(b.bridge.rows[0].read).toBeNull();
    expect(b.bridge.rows[0].driver).toBe('BTC');
    expect(b.news.map((n) => n.kind)).toEqual(['catalyst']);
    expect(b.next.map((n) => n.kind)).toEqual(['funding']);
    expect(b.sources).toEqual([{ id: 'coingecko', label: 'coingecko', ok: null, at: null, error: null }]);
  });
});

describe('normalizeCandles', () => {
  it('keeps whole candles only, and an unknown volume unknown', () => {
    const c = normalizeCandles({
      schema_version: 1,
      symbol: 'BTC',
      tf: '15m',
      candles: [{ t: 0, o: 1, h: 2, l: 0.5, c: 1.5, v: 3 }, { t: 900, o: 1, h: 2, l: 0.5, c: 1.5 }, { t: 1800, o: 1, h: 2, c: 1 }],
      levels: { high_24h: 2, stock_close: { at: 900 } },
      sessions: [{ kind: 'regular', start: 0, end: 900 }, { kind: 'lunch', start: 0, end: 1 }],
    })!;
    expect(c.candles.map((x) => x.v)).toEqual([3, null]);
    expect(c.levels.high_24h).toBe(2);
    expect(c.levels.day_open).toBeNull();
    expect(c.levels.stock_close).toBeNull();
    expect(c.sessions).toHaveLength(1);
    expect(normalizeCandles({ schema_version: 1, tf: '5m' })!.tf).toBe('15m');
    expect(normalizeCandles({ schema_version: 0 })).toBeNull();
  });
});
