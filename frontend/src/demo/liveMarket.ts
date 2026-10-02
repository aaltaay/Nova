/**
 * The demo's moving market (ADR 043): for each symbol a socket watches, prints arrive every second
 * or so at the bid or the ask, the book's sizes shift and the quote steps a cent now and then,
 * inside a narrow band around the sample price (SMPL never reaches its 4.38 trigger, so the plan
 * on screen stays true). Nova Marketing Sample Data: nothing here is a market.
 */
import { SMPL, rowFor } from './data/desk';
import { r2, rng, sampleBook, type BookRow, type SamplePrint } from './data/market';

export interface LiveState {
  symbol: string;
  last: number;
  bid: number;
  ask: number;
  dayVolume: number;
  bids: BookRow[];
  asks: BookRow[];
}

export interface LiveListener {
  print?: (p: SamplePrint, s: LiveState) => void;
  book?: (s: LiveState) => void;
}

interface Market {
  state: LiveState;
  low: number;
  high: number;
  tick: number;
  rand: () => number;
  listeners: Set<LiveListener>;
  timer: ReturnType<typeof setTimeout> | null;
}

const markets = new Map<string, Market>();

function basePrice(symbol: string): number {
  return symbol === 'SMPL' ? SMPL.last : rowFor(symbol).price;
}

function create(symbol: string): Market {
  const last = basePrice(symbol);
  const step = last < 1 ? 0.0001 : 0.01;
  const book = sampleBook(last);
  return {
    state: { symbol, last, bid: r2(last - 0.01), ask: last, dayVolume: rowFor(symbol).volume, bids: book.bids, asks: book.asks },
    // SMPL stays between 4.30 and 4.35; anything else within about half a percent.
    low: symbol === 'SMPL' ? 4.3 : r2(Math.max(step, last * 0.995)),
    high: symbol === 'SMPL' ? 4.35 : r2(last * 1.005),
    tick: 0,
    rand: rng(symbol.split('').reduce((a, c) => a * 31 + c.charCodeAt(0), 7)),
    listeners: new Set(),
    timer: null,
  };
}

function jitterBook(m: Market): void {
  const { state, rand } = m;
  for (let i = 0; i < 3; i += 1) {
    const side = rand() < 0.5 ? state.bids : state.asks;
    const row = side[Math.floor(rand() * Math.min(side.length, 8))];
    if (row) row.size = Math.max(100, row.size + (rand() < 0.5 ? -1 : 1) * Math.round(1 + rand() * 8) * 100);
  }
}

function step(m: Market): void {
  const { state, rand } = m;
  m.tick += 1;
  // Now and then the quote steps a cent, inside the band.
  if (rand() < 0.12) {
    const up = rand() < 0.55;
    const next = r2(state.ask + (up ? 0.01 : -0.01));
    if (next >= m.low + 0.01 && next <= m.high) {
      const book = sampleBook(next, 3 + m.tick);
      Object.assign(state, { ask: next, bid: r2(next - 0.01), bids: book.bids, asks: book.asks });
    }
  } else {
    jitterBook(m);
  }
  const lift = rand() < 0.62;
  const odd = rand() < 0.1;
  const size = odd ? [10, 25, 40, 50, 75][Math.floor(rand() * 5)] : Math.round(1 + rand() * (rand() < 0.1 ? 40 : 9)) * 100;
  const price = lift ? state.ask : state.bid;
  const print: SamplePrint = { ms: Date.now(), price, size, side: lift ? 'ask' : 'bid', bid: state.bid, ask: state.ask };
  state.last = price;
  state.dayVolume += size;
  for (const l of m.listeners) {
    l.print?.(print, state);
    l.book?.(state);
  }
}

function schedule(m: Market): void {
  m.timer = setTimeout(() => {
    step(m);
    if (m.listeners.size > 0) schedule(m);
  }, 450 + Math.floor(m.rand() * 1100));
}

/** Watch a symbol's sample market; returns the current state and a stop function. */
export function watchMarket(symbol: string, listener: LiveListener): { state: LiveState; stop: () => void } {
  let m = markets.get(symbol);
  if (!m) {
    m = create(symbol);
    markets.set(symbol, m);
  }
  const market = m;
  market.listeners.add(listener);
  if (!market.timer) schedule(market);
  return {
    state: market.state,
    stop: () => {
      market.listeners.delete(listener);
      if (market.listeners.size === 0 && market.timer) {
        clearTimeout(market.timer);
        market.timer = null;
      }
    },
  };
}

/** The last sample price a socket printed for `symbol` (the sample price before any). */
export function livePrice(symbol: string): number {
  return markets.get(symbol)?.state.last ?? basePrice(symbol);
}
