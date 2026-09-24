import type { Page, Route } from '@playwright/test';
import { E2E_ACCOUNT, E2E_IBKR_STATUS } from '../fixtures/orderRows';
import { routeSampleBars } from './sampleBars';

/**
 * The live Trader route with a mocked Nova API.
 *
 * `?view=sample` refuses every backend read inside the page
 * (src/sample_data/sampleNetworkGate.ts), so a `page.route` mock never sees a
 * request there and the charts stay empty. Specs that need served candles, a
 * tape print or a held position open the live route instead and answer
 * `/api/**` here -- the way open-closed-orders.spec.ts does.
 *
 * Nothing reaches a broker: every order mutation is answered 403 and recorded
 * in the returned list, which a spec can assert stays empty.
 */

/** A held long, so the chart draws its position tag and Close Position row. */
export const E2E_POSITION_SMPL = {
  symbol: 'SMPL',
  qty: 200,
  market_price: 4.25,
  market_value: 850,
  avg_cost: 3.1,
  unrealized_pnl: 230,
  realized_pnl: 0,
};

/**
 * `GET /api/ticker/<sym>`: the Trader rail (quote card, ticket) waits on a
 * quote, which the sample desk used to take from its own fixture.
 */
export function e2eTickerDetail(symbol: string, price = 4.25, prevClose = 2.8) {
  const ts = '2026-09-11T13:29:55.000Z';
  const bar = (open: number, high: number, low: number, close: number, volume: number) => ({
    open, high, low, close, volume, trade_count: null, vwap: null, timestamp: null,
  });
  return {
    symbol,
    mode: 'regular',
    avg_volume: 2_500_000,
    rel_volume: 12,
    news: [],
    news_impact: null,
    fundamentals: null,
    asset: { name: `${symbol} E2E Co`, exchange: 'NASDAQ', tradable: true, shortable: true },
    snapshot: {
      latest_trade: { price, size: 200, exchange: 'Q', timestamp: ts },
      latest_quote: {
        bid_price: price - 0.01,
        bid_size: 500,
        ask_price: price + 0.01,
        ask_size: 500,
        timestamp: ts,
      },
      minute_bar: null,
      daily_bar: bar(prevClose * 1.05, price * 1.08, prevClose * 0.98, price, 10_000_000),
      prev_daily_bar: bar(prevClose * 0.99, prevClose * 1.02, prevClose * 0.97, prevClose, 3_000_000),
      prev_close: prevClose,
      session_close: null,
      session_prev_close: null,
    },
  };
}

async function json(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

const HARD_BAN = { ok: false, error: 'e2e hard-ban: no place/cancel from a Trader spec' };

export interface LiveTraderApiOptions {
  /** Held positions (`/api/ibkr/positions`); defaults to SMPL 200 long. */
  positions?: unknown[];
  /** Serve deterministic candles on `/api/ticker/<sym>/bars` (default true). */
  bars?: boolean;
}

/** Mock the reads a Trader tab makes; returns every order mutation it refused. */
export async function mockLiveTraderApi(
  page: Page,
  options: LiveTraderApiOptions = {},
): Promise<{ mutations: string[] }> {
  const mutations: string[] = [];
  const positions = options.positions ?? [E2E_POSITION_SMPL];

  await page.route('**/api/ticker/*', (route) => {
    const symbol = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop() ?? '');
    return json(route, e2eTickerDetail(symbol.toUpperCase()));
  });
  await page.route('**/api/ibkr/status', (route) => json(route, E2E_IBKR_STATUS));
  await page.route('**/api/ibkr/account', (route) => json(route, E2E_ACCOUNT));
  await page.route('**/api/ibkr/positions', (route) => json(route, positions));
  await page.route('**/api/ibkr/orders**', (route) => json(route, []));
  // Place / cancel / flatten -- refused, never forwarded.
  await page.route(/\/api\/ibkr\/(order|flatten-account)(\/|$|\?)/, async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      await json(route, []);
      return;
    }
    mutations.push(`${request.method()} ${request.url()}`);
    await json(route, HARD_BAN, 403);
  });
  if (options.bars !== false) await routeSampleBars(page);
  return { mutations };
}
