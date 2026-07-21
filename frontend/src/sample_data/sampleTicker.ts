/** Sample ticker detail for Trader when ?view=sample&symbol=… */
import { makeDetail } from '../modules/quoteFixtures';
import type { TickerDetail } from '../types/ticker';
import { SAMPLE_CATALYSTS, SAMPLE_GAPPERS, SAMPLE_GAINERS } from './sampleRows';

const NAMES: Record<string, string> = {
  SMPL: 'Sample Pharma Inc',
  GAPX: 'Gapper Example Corp',
  MOMO: 'Momo Runner Ltd',
  NWSR: 'NewsWire Chatter Co',
  RUNR: 'Runner Dynamics',
  SPIK: 'Spike Microcap',
  GAPX2: 'Unused',
};

export function sampleTickerDetail(symbol: string): TickerDetail {
  const key = symbol.trim().toUpperCase();
  const row =
    SAMPLE_GAPPERS.find((r) => r.symbol === key) ||
    SAMPLE_GAINERS.find((r) => r.symbol === key) ||
    null;
  const cat = SAMPLE_CATALYSTS.find((c) => c.symbol === key);
  const price = row?.price ?? cat?.current_price ?? 4.25;
  const prev = row?.prev_close ?? cat?.previous_close ?? 2.8;
  return makeDetail({
    symbol: key,
    mode: 'regular',
    avg_volume: 2_500_000,
    rel_volume: row?.rel_volume ?? 12,
    rvol_5min: 6.5,
    volume_in_5min: 400_000,
    news_impact: cat?.news_impact ?? null,
    news: cat?.catalyst_headline
      ? [
          {
            headline: cat.catalyst_headline,
            summary: cat.catalyst_headline,
            author: 'Sample',
            source: cat.catalyst_source ?? 'Sample',
            url: cat.catalyst_url ?? 'https://example.com/news',
            created_at: cat.newest_headline_at ?? new Date().toISOString(),
            symbols: [key],
            images: [],
          },
        ]
      : [],
    asset: {
      name: NAMES[key] ?? `${key} Sample Co`,
      exchange: row?.exchange ?? 'NASDAQ',
      tradable: true,
      shortable: true,
      easy_to_borrow: true,
      marginable: true,
    },
    listing: {
      symbol: key,
      alpaca: {
        source: 'alpaca_assets',
        status: 'active',
        tradable: true,
        shortable: true,
        easy_to_borrow: true,
        short_type: 'easy_to_borrow',
        short_type_detail: 'Sample Alpaca ETB — not IBKR locate',
        marginable: true,
        fractionable: true,
        maintenance_margin_requirement: 30,
        margin_requirement_long: null,
        margin_requirement_short: null,
        asset_class: 'us_equity',
        exchange: row?.exchange ?? 'NASDAQ',
        attributes: [],
        error: null,
      },
      ibkr: {
        source: 'ibkr',
        connected: true,
        qualified: true,
        con_id: 1,
        long_name: NAMES[key] ?? `${key} Sample Co`,
        stock_type: 'COMMON',
        exchange: 'NASDAQ',
        shortable_shares: 250_000,
        short_type: 'available',
        short_type_detail: 'Sample IBKR shortableShares',
        tradable_hint: 'qualified',
        error: null,
      },
    },
    snapshot: {
      latest_trade: {
        price,
        size: 200,
        exchange: 'Q',
        timestamp: new Date().toISOString(),
      },
      latest_quote: {
        bid_price: price - 0.01,
        bid_size: 500,
        ask_price: price + 0.01,
        ask_size: 500,
        timestamp: new Date().toISOString(),
      },
      minute_bar: null,
      daily_bar: {
        open: prev * 1.05,
        high: price * 1.08,
        low: prev * 0.98,
        close: price,
        volume: row?.volume ?? 10_000_000,
        trade_count: null,
        vwap: (price + prev) / 2,
        timestamp: null,
      },
      prev_daily_bar: {
        open: prev * 0.99,
        high: prev * 1.02,
        low: prev * 0.97,
        close: prev,
        volume: 3_000_000,
        trade_count: null,
        vwap: null,
        timestamp: null,
      },
      prev_close: prev,
      session_close: null,
      session_prev_close: null,
    },
    fundamentals: {
      market_cap: row?.market_cap ?? 50_000_000,
      shares_outstanding: (row?.float ?? 10_000_000) * 1.2,
      float_shares: row?.float ?? 10_000_000,
      short_interest: row?.short_interest ?? 1_000_000,
      short_ratio: row?.short_ratio ?? 1,
      short_percent_of_float: null,
      pe_ratio: null,
      forward_pe: null,
      eps: null,
      sector: 'Healthcare',
      industry: 'Biotechnology',
      fifty_two_week_high: price * 1.4,
      fifty_two_week_low: prev * 0.5,
      dividend_yield: null,
      beta: null,
      earnings_date: null,
      recent_split: null,
    },
  });
}
