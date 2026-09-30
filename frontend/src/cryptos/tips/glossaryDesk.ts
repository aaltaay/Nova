/**
 * What the Cryptos page's clock, stocks bridge, flows, calendar and news mean (ADR 040): the hover cards' words
 * for the lower half of the page. See glossaryMarket.ts for the tiles, the table and the chart.
 */
import { BRIDGE_READ_BAND_PT, COLORS } from '../constants';
import { countdown, dateEt, dayTimeEt, minutesEt, pct, stockPrice, timeEt, usd, usdSigned } from '../format';
import type { BridgePhase, BridgeRow, CryptoClock, NewsKind, NewsRow, NextEvent, Stablecoins } from '../types';
import type { TipContent } from './TipHost';

export const BRIDGE_ABOUT: Record<string, string> = {
  IBIT: 'iShares Bitcoin Trust: an ETF that holds bitcoin. It moves one-for-one with BTC, but only in stock hours.',
  ETHA: 'iShares Ethereum Trust: an ETF that holds ether.',
  MSTR: 'Strategy (formerly MicroStrategy): a company sitting on a huge bitcoin treasury. It trades like leveraged bitcoin.',
  COIN: 'Coinbase: the largest US crypto exchange. It earns more when crypto is busy.',
  MARA: 'A bitcoin miner: its profits swing with the bitcoin price, so it moves more than BTC does.',
  RIOT: 'A bitcoin miner: its profits swing with the bitcoin price, so it moves more than BTC does.',
  CLSK: 'CleanSpark, a bitcoin miner: its profits swing with the bitcoin price.',
  HOOD: 'Robinhood: a broker with a big crypto trading business.',
};

const PHASE_WORDS: Record<BridgePhase, string> = {
  premarket: 'premarket',
  regular: 'today',
  after_hours: 'after hours',
  overnight: 'after hours',
};

export function phaseLabel(phase: BridgePhase): string {
  return phase === 'premarket' ? 'Premarket' : phase === 'regular' ? 'Today' : 'After hrs';
}

function nowMinutes(clock: CryptoClock): number {
  const [h, m] = timeEt(clock.now).split(':').map(Number);
  return (h || 0) * 60 + (m || 0);
}

export function tipLane(kind: 'crypto' | 'asia' | 'europe' | 'us' | 'funding' | 'now', clock: CryptoClock): TipContent {
  const base = { visual: { kind: 'sessions' as const, lanes: clock.lanes, nowMin: nowMinutes(clock), highlight: [] as ('crypto' | 'asia' | 'europe' | 'premarket' | 'regular' | 'after_hours' | 'funding')[] } };
  const span = (l: [number, number][]) => l.map(([a, b]) => `${minutesEt(a)}–${minutesEt(b)}`).join(' and ');
  switch (kind) {
    case 'crypto':
      return { ...base, visual: { ...base.visual, highlight: ['crypto'] }, title: 'Crypto: open 24/7', tone: 'up',
        what: `Crypto trades every minute of every day, weekends and holidays too. Its "day" resets at 00:00 UTC (${clock.crypto_day_start_et} ET now).`,
        why: 'News at 2 a.m. or on a Sunday moves crypto at once; stocks only catch up at their next open.' };
    case 'asia':
      return { ...base, visual: { ...base.visual, highlight: ['asia'] }, title: 'Asia session (Tokyo, Hong Kong)', tone: 'violet',
        what: `Asia’s market hours: ${span(clock.lanes.asia) || 'closed today'} ET.`,
        now: clock.regions.asia ? 'Asia is trading now.' : 'Asia is closed now.',
        why: 'Often quieter; a big move here sets up the US premarket.' };
    case 'europe':
      return { ...base, visual: { ...base.visual, highlight: ['europe'] }, title: 'Europe session (London)', tone: 'accent',
        what: `London’s market hours: ${span(clock.lanes.europe) || 'closed today'} ET. It overlaps the US premarket.`,
        now: clock.regions.europe ? 'Europe is trading now.' : 'Europe is closed now.',
        why: 'European money often starts the day’s trend before New York wakes up.' };
    case 'us':
      return { ...base, visual: { ...base.visual, highlight: ['premarket', 'regular', 'after_hours'] }, title: 'US stock sessions', tone: 'up',
        what: clock.lanes.regular.length
          ? 'Premarket 04:00–09:30, open 09:30–16:00, after hours 16:00–20:00 ET. Crypto stocks and ETFs trade only here.'
          : 'US stocks do not trade today. Crypto stocks and ETFs wait for the next session.',
        now: clock.stock_next ? `Next: ${nextStockWords(clock.stock_next.kind)} in ${countdown(clock.stock_next.at - clock.now)}.` : null };
    case 'funding':
      return { ...base, visual: { ...base.visual, highlight: ['funding', 'crypto'] }, title: 'Funding settlements', tone: 'warn',
        what: `The big futures exchanges settle funding every 8 hours: 00:00, 08:00 and 16:00 UTC (${clock.lanes.funding.map(([m]) => minutesEt(m)).join(', ')} ET).`,
        now: `Next in ${countdown(clock.next_funding - clock.now)}.`,
        why: 'Traders close crowded bets just before a settlement to avoid paying it, which can nudge the price.' };
    default:
      return { ...base, title: `Now ${timeEt(clock.now)} ET`, tone: 'muted', what: 'Where the day is: which markets are open right now.' };
  }
}

function nextStockWords(kind: string): string {
  return kind === 'premarket' ? 'premarket opens' : kind === 'open' ? 'stocks open' : kind === 'close' ? 'stocks close' : 'after hours ends';
}

export function tipBridgeSymbol(r: BridgeRow): TipContent {
  return {
    title: `${r.symbol} · ${r.what}`,
    tone: 'accent',
    what: BRIDGE_ABOUT[r.symbol] ?? `${r.symbol} moves with ${r.driver}.`,
    visual: r.beta === null ? undefined : { kind: 'flow', steps: [`${r.driver} moves 1%`, `×${r.beta.toFixed(1)}`, `${r.symbol} ≈ ${r.beta.toFixed(1)}%`] },
    why: 'Click to open it in the Trader.',
    source: 'IBKR prices.',
  };
}

export function tipBeta(r: BridgeRow): TipContent {
  return {
    title: `Beta ${r.beta === null ? 'unknown' : `${r.beta.toFixed(1)}×`}`,
    tone: 'accent',
    what: `How much ${r.symbol} usually moves for each 1% ${r.driver} moves, measured over the last 60 trading days.`,
    visual: r.beta === null ? undefined : { kind: 'formula', parts: [
      { label: r.driver, value: '+1%' }, { label: 'beta', value: `${r.beta.toFixed(1)}×` },
      { label: r.symbol, value: `≈ +${r.beta.toFixed(1)}%`, tone: 'accent' },
    ], ops: ['×', '='] },
    now: r.beta === null ? 'Not enough shared history yet (needs 20 sessions of IBKR closes and Coinbase prices).' : null,
    why: 'Higher beta = more leverage to crypto, both ways.',
    source: 'IBKR regular-session closes against Coinbase’s 16:00 ET prices.',
  };
}

export function tipClose(r: BridgeRow, refAt: number | null): TipContent {
  return {
    title: 'Last close · 16:00 ET',
    tone: 'muted',
    what: `${r.symbol}’s official regular-session close${refAt ? ` on ${dateEt(refAt)}` : ''}. Every move on this row is measured from it.`,
    now: r.close === null ? 'Unknown: IBKR has not answered yet.' : `$${stockPrice(r.close)}.`,
    source: 'IBKR daily bars, regular hours only.',
  };
}

export function tipSince(r: BridgeRow, phase: BridgePhase): TipContent {
  return {
    title: `${r.symbol} ${PHASE_WORDS[phase]}`,
    tone: (r.since_close_pct ?? 0) >= 0 ? 'up' : 'down',
    what: `${r.symbol}’s move since that close, from its latest trade on IBKR.`,
    now: r.since_close_pct === null ? 'No trade since the close yet: unknown, not zero.' : `${pct(r.since_close_pct, 1)} (last $${stockPrice(r.last)}).`,
    source: 'IBKR snapshot, refreshed every minute while this page is open.',
  };
}

export function tipImplied(r: BridgeRow, move: number | null): TipContent {
  return {
    title: `What ${r.driver} implies for ${r.symbol}`,
    tone: 'up',
    what: `${r.driver}’s move since the stock close × ${r.symbol}’s beta: what the stock would be doing if it followed ${r.driver} exactly.`,
    visual: { kind: 'formula', parts: [
      { label: `${r.driver} since`, value: pct(move) }, { label: 'beta', value: r.beta === null ? '?' : `${r.beta.toFixed(1)}×` },
      { label: 'implied', value: pct(r.implied_pct, 1), tone: (r.implied_pct ?? 0) >= 0 ? 'up' : 'down' },
    ], ops: ['×', '='] },
    why: 'A hint, never a price: news of its own can move the stock anyway.',
  };
}

export function tipRead(r: BridgeRow): TipContent {
  const color = r.read === 'ahead' ? COLORS.up : r.read === 'behind' ? COLORS.warn : COLORS.muted;
  const words = r.read === 'ahead' ? `ahead by ${Math.abs(r.gap_pt ?? 0).toFixed(1)} points: ${r.symbol} already moved more than ${r.driver} implies`
    : r.read === 'behind' ? `behind by ${Math.abs(r.gap_pt ?? 0).toFixed(1)} points: ${r.symbol} has not caught up with ${r.driver} yet`
      : r.read === 'in_line' ? `in line (within ${BRIDGE_READ_BAND_PT} points)` : 'unknown until both numbers are known';
  return {
    title: 'Ahead, behind or in line',
    tone: r.read === 'ahead' ? 'up' : r.read === 'behind' ? 'warn' : 'muted',
    what: `The stock’s actual move against what ${r.driver} implies.`,
    visual: { kind: 'compare', rows: [
      { label: 'Actual', value: r.since_close_pct, text: pct(r.since_close_pct, 1), color },
      { label: 'Implied', value: r.implied_pct, text: pct(r.implied_pct, 1), color: COLORS.muted },
    ] },
    now: `${r.symbol} is ${words}.`,
    why: 'Behind: the stock may catch up at the open. Ahead: it already priced in more than crypto did, so it can give some back.',
  };
}

export function tipStablecoins(s: Stablecoins | null, index: number | null): TipContent {
  const days = s?.daily ?? [];
  const day = index === null ? days[days.length - 1] : days[index];
  return {
    title: 'Stablecoins minted, day by day',
    tone: 'up',
    what: 'New digital dollars (USDT, USDC ...) created (green) or redeemed (red) each day. Fresh stablecoins are cash waiting to buy crypto.',
    visual: { kind: 'bars', values: days.map((d) => d.net_usd), labels: days.map((d) => d.date.slice(8)), highlight: index ?? days.length - 1 },
    now: day ? `${day.date}: ${usdSigned(day.net_usd)}. Supply ${usd(s?.supply_usd ?? null)}.` : 'Unknown: DefiLlama has not answered.',
    why: 'Steady minting is dry powder for the next leg up; redemptions mean money leaving crypto.',
    source: 'DefiLlama, USD-pegged stablecoins.',
  };
}

export function tipEtfFlows(note: string | null): TipContent {
  return {
    title: 'Spot bitcoin ETF flows',
    tone: 'muted',
    what: 'Dollars moving into or out of the US spot bitcoin ETFs each day. Inflows mean the funds must buy bitcoin.',
    visual: { kind: 'flow', steps: ['Investors buy IBIT', 'Fund buys BTC', 'BTC demand'] },
    now: 'Not shown on this desk yet.',
    source: note ?? 'No free source publishes them as data.',
  };
}

export function tipNext(e: NextEvent, clock: CryptoClock): TipContent {
  const inTime = `${dayTimeEt(e.at)} ET, in ${countdown(e.at - clock.now)}.`;
  if (e.kind === 'expiry') {
    return { title: e.title, tone: 'violet',
      what: 'Bitcoin options on Deribit expire every Friday at 08:00 UTC; the month’s last Friday is the big one.',
      now: `${inTime}${e.detail ? ` ${e.detail}.` : ''}`,
      why: 'Before a big expiry the price can get pinned near popular strike prices, then move freely after.' };
  }
  if (e.kind === 'stocks') {
    return { title: e.title, tone: 'up', what: 'The next change in the US stock session: when crypto stocks can trade again, or stop.',
      visual: { kind: 'sessions', lanes: clock.lanes, highlight: ['premarket', 'regular', 'after_hours'], nowMin: nowMinutes(clock) }, now: inTime };
  }
  return { title: e.title, tone: 'warn', what: e.detail ?? '', now: inTime,
    visual: { kind: 'sessions', lanes: clock.lanes, highlight: ['funding', 'crypto'], nowMin: nowMinutes(clock) } };
}

export const NEWS_TAG: Record<NewsKind, { label: string; color: string; text: string }> = {
  catalyst: { label: 'Catalyst', color: COLORS.up, text: 'Something happened that can move the coin.' },
  negative: { label: 'Negative', color: COLORS.down, text: 'A hack, a lawsuit, a delisting, new supply.' },
  news: { label: 'News', color: COLORS.accent, text: 'About the coin, but not a clear cause.' },
  noise: { label: 'Noise', color: COLORS.muted, text: 'The price talking about itself.' },
};

export function tipNews(n: NewsRow, now: number): TipContent {
  const mins = Math.max(0, Math.round((now - n.published_ts) / 60));
  return {
    title: `${n.symbol} · ${NEWS_TAG[n.kind].label}`,
    tone: n.kind === 'catalyst' ? 'up' : n.kind === 'negative' ? 'down' : 'muted',
    what: `“${n.title}”`,
    visual: { kind: 'tags', items: (Object.keys(NEWS_TAG) as NewsKind[]).map((k) => ({ ...NEWS_TAG[k], active: k === n.kind })) },
    now: `${n.source ?? 'Alpaca'} · ${mins < 60 ? `${mins} min` : `${Math.floor(mins / 60)} h ${mins % 60} min`} ago (${timeEt(n.published_ts)} ET).`,
    why: n.kind === 'noise' ? 'Noise is dimmed: it repeats the price, it does not explain it.' : null,
  };
}

export function tipCryptoOpen(clock: CryptoClock): TipContent {
  return tipLane('crypto', clock);
}

export function tipStocksStatus(clock: CryptoClock): TipContent {
  return tipLane('us', clock);
}
