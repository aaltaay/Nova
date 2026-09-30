/**
 * What every number on the Cryptos page's tiles, coins table and chart means (ADR 040): one place for the words,
 * so the page says each thing the same way everywhere. Each builder takes the live reading and answers the hover
 * card; an unknown reading says it is unknown and why.
 */
import { COLORS, FEAR_GREED_ZONES, FUNDING_CROWDED_PCT, FUNDING_SHORTS_PCT, VOLUME_HOT_X } from '../constants';
import { funding, level, mult, pct, price, pt, usd } from '../format';
import type { CryptoCandles, CryptoCoin, CryptoMarket, SourceStatus } from '../types';
import type { TipContent } from './TipHost';

export const COIN_ABOUT: Record<string, string> = {
  BTC: 'The first cryptocurrency: digital money with a fixed supply of 21 million coins.',
  ETH: 'The coin of Ethereum, the network most crypto apps and tokens run on.',
  SOL: 'The coin of Solana, a fast network popular for trading apps and meme coins.',
  XRP: 'The coin of the XRP Ledger, built for moving money between banks.',
  BNB: 'The coin of Binance, the largest crypto exchange, and of its BNB Chain.',
  DOGE: 'The original meme coin: it moves on attention and social media, not a product.',
  ADA: 'The coin of Cardano, a research-driven blockchain.',
  LINK: 'Chainlink feeds real-world prices and data into blockchains.',
  SUI: 'The coin of Sui, a newer, fast blockchain.',
  AVAX: 'The coin of Avalanche, a network of fast blockchains.',
  BCH: 'Bitcoin Cash: a 2017 split from bitcoin, aimed at payments.',
  LTC: 'Litecoin, one of the oldest coins, often called the silver to bitcoin’s gold.',
  PEPE: 'A meme coin named after the frog meme: very fast, very crowded.',
};

const SRC_COINGECKO = 'CoinGecko: the average across the big exchanges, refreshed every minute while this page is open.';
const SRC_HYPERLIQUID = 'Hyperliquid perpetual futures: its hourly funding rate × 8.';

export function fundingWords(rate: number | null): string {
  if (rate === null) return 'unknown';
  if (rate >= FUNDING_CROWDED_PCT) return 'longs are crowded';
  if (rate <= FUNDING_SHORTS_PCT) return 'shorts are crowded';
  return 'calm';
}

export function tipCoinPrice(c: CryptoCoin): TipContent {
  const tone = (c.change_24h_pct ?? 0) >= 0 ? 'up' : 'down';
  const ath = c.from_ath_pct === null ? '' : ` · ${Math.abs(c.from_ath_pct).toFixed(1)}% under its all-time high`;
  return {
    title: `${c.name} · ${c.symbol}`,
    tone,
    what: `${c.name}'s price in US dollars. ${COIN_ABOUT[c.symbol] ?? ''}`.trim(),
    visual: { kind: 'range', low: c.low_24h, high: c.high_24h, value: c.price, mark: price(c.price),
      lowLabel: `24h low ${price(c.low_24h)}`, highLabel: `24h high ${price(c.high_24h)}` },
    now: c.price === null ? 'Unknown: CoinGecko has not answered yet.' : `${pct(c.change_24h_pct)} in 24 hours${ath}.`,
    why: c.symbol === 'BTC'
      ? 'Bitcoin sets the mood: when it moves, most coins and the crypto stocks below follow.'
      : c.symbol === 'ETH'
        ? 'Ether leads the other coins: when ETH beats BTC, traders are reaching for more risk.'
        : 'Where the price sits in its day tells you who is winning: near the high, buyers; near the low, sellers.',
    source: SRC_COINGECKO,
  };
}

export function tipChanges(c: CryptoCoin): TipContent {
  const row = (label: string, v: number | null) => ({ label, value: v, text: pct(v, 1), color: (v ?? 0) >= 0 ? COLORS.up : COLORS.down });
  return {
    title: `${c.symbol}: how far it moved`,
    tone: (c.change_24h_pct ?? 0) >= 0 ? 'up' : 'down',
    what: 'The price now against 1 hour, 24 hours and 7 days ago.',
    visual: { kind: 'compare', rows: [row('1 hour', c.change_1h_pct), row('24 hours', c.change_24h_pct), row('7 days', c.change_7d_pct)] },
    why: 'All three the same colour = a steady trend. A green hour inside a red week = a bounce, not a turn.',
    source: SRC_COINGECKO,
  };
}

export function tipSpark(c: CryptoCoin): TipContent {
  return {
    title: `${c.symbol}: the last 7 days`,
    tone: (c.change_7d_pct ?? 0) >= 0 ? 'up' : 'down',
    what: 'The price path over the past week, one point every two hours.',
    visual: { kind: 'spark', values: c.spark_7d, up: (c.change_7d_pct ?? 0) >= 0, startLabel: '7 days ago', endLabel: 'now' },
    now: c.change_7d_pct === null ? null : `${pct(c.change_7d_pct, 1)} over 7 days.`,
    why: 'A steady staircase is a trend; one spike then a slide is a pump that faded.',
    source: SRC_COINGECKO,
  };
}

export function tipVolume(c: CryptoCoin): TipContent {
  const hot = c.volume_x_30d !== null && c.volume_x_30d >= VOLUME_HOT_X;
  return {
    title: `${c.symbol}: volume`,
    tone: hot ? 'warn' : 'accent',
    what: 'Dollars of this coin traded in the last 24 hours, across exchanges, against its usual day (the 30-day average).',
    visual: { kind: 'compare', rows: [
      { label: 'Last 24 h', value: c.volume_x_30d, text: mult(c.volume_x_30d), color: hot ? COLORS.warn : COLORS.accent },
      { label: 'Usual day', value: c.volume_x_30d === null ? null : 1, text: '1.0×', color: COLORS.muted },
    ] },
    now: c.volume_24h_usd === null ? 'Unknown.' : `${usd(c.volume_24h_usd)} traded${c.volume_x_30d === null ? ' (its usual day is not known yet)' : `, ${mult(c.volume_x_30d)} a usual day`}.`,
    why: hot ? 'Twice its usual volume or more: something is happening. Moves on heavy volume tend to stick.' : 'Moves on thin volume fade easily; moves on heavy volume tend to stick.',
    source: SRC_COINGECKO,
  };
}

export function tipCap(c: CryptoCoin): TipContent {
  return {
    title: `${c.symbol}: market value`,
    what: 'The price × every coin in circulation: what the whole coin is worth.',
    visual: { kind: 'formula', parts: [{ label: 'price', value: price(c.price) }, { label: 'coins', value: 'supply' }, { label: 'value', value: usd(c.market_cap_usd), tone: 'accent' }], ops: ['×', '='] },
    now: c.rank === null ? null : `#${c.rank} of all coins by market value.`,
    why: 'Big coins need big money to move; small ones can double on a rumour.',
    source: SRC_COINGECKO,
  };
}

export function tipFunding(symbol: string, rate: number | null, oiUsd?: number | null): TipContent {
  const words = fundingWords(rate);
  return {
    title: `${symbol} funding · per 8 h`,
    tone: words === 'longs are crowded' ? 'warn' : words === 'shorts are crowded' ? 'accent' : 'up',
    what: 'What traders with leveraged futures pay each other every 8 hours to keep their bets open. Positive: buyers (longs) pay sellers (shorts).',
    visual: { kind: 'scale', min: -0.05, max: 0.07, value: rate, mark: funding(rate), zones: [
      { to: FUNDING_SHORTS_PCT, label: 'Shorts crowded', color: COLORS.cool },
      { to: FUNDING_CROWDED_PCT, label: 'Calm', color: COLORS.up },
      { to: 0.07, label: 'Longs crowded', color: COLORS.warn },
    ] },
    now: rate === null ? 'Unknown: Hyperliquid has not answered.' : `${funding(rate)} per 8 h: ${words}.${oiUsd ? ` Open bets on Hyperliquid: ${usd(oiUsd)}.` : ''}`,
    why: 'When longs are crowded, a small dip can force them all out at once (a flush). Crowded shorts can be squeezed up.',
    source: SRC_HYPERLIQUID,
  };
}

export function tipTotalCap(m: CryptoMarket): TipContent {
  return {
    title: 'Crypto market cap',
    tone: (m.total_cap_change_24h_pct ?? 0) >= 0 ? 'up' : 'down',
    what: 'Every coin’s price × its coins in circulation, added up: the size of the whole crypto market. The little line is the 13 coins on this page, combined, over the last 24 hours.',
    visual: { kind: 'formula', parts: [{ label: 'each coin', value: 'price' }, { label: 'coins', value: 'supply' }, { label: 'all coins', value: usd(m.total_cap_usd), tone: 'accent' }], ops: ['×', '→'] },
    now: m.total_cap_usd === null ? 'Unknown.' : `${usd(m.total_cap_usd)}, ${pct(m.total_cap_change_24h_pct)} in 24 hours.`,
    why: 'A rising total means new money is coming in, not just moving between coins.',
    source: 'CoinGecko /global.',
  };
}

export function tipDominance(m: CryptoMarket): TipContent {
  const d = m.btc_dominance_pct;
  const ch = m.btc_dominance_change_24h_pt;
  const move = ch === null ? '' : ch < 0 ? ': other coins rose faster than bitcoin (alts leading)' : ch > 0 ? ': bitcoin held up better (money hiding in BTC)' : '';
  return {
    title: 'Bitcoin dominance',
    tone: 'warn',
    what: 'Bitcoin’s share of the whole crypto market’s value.',
    visual: d === null ? undefined : { kind: 'split', left: { label: `BTC ${d.toFixed(1)}%`, value: d, color: '#f7931a' }, right: { label: `Everything else ${(100 - d).toFixed(1)}%`, value: 100 - d, color: COLORS.violet } },
    now: d === null ? 'Unknown.' : `${d.toFixed(1)}%, ${pt(ch)} in 24 hours${move}.`,
    why: 'Falling dominance on a green day = money spreading into riskier coins. Rising dominance on a red day = fear, money retreating to bitcoin.',
    source: 'CoinGecko; the 24-hour change is worked out from its own 24-hour changes.',
  };
}

export function tipTotalVolume(m: CryptoMarket): TipContent {
  return {
    title: '24-hour volume',
    tone: (m.volume_x_30d ?? 1) >= VOLUME_HOT_X ? 'warn' : 'accent',
    what: 'Dollars traded in the last 24 hours across the whole crypto market.',
    visual: { kind: 'compare', rows: [
      { label: 'Last 24 h', value: m.volume_x_30d, text: mult(m.volume_x_30d, 2), color: COLORS.accent },
      { label: 'Usual day', value: m.volume_x_30d === null ? null : 1, text: '1.00×', color: COLORS.muted },
    ], note: 'Measured on the 13 coins on this page against their own 30-day average.' },
    now: m.total_volume_usd === null ? 'Unknown.' : `${usd(m.total_volume_usd)} traded.`,
    why: 'Busier than usual = conviction behind the move. Quiet = the move can reverse easily.',
    source: 'CoinGecko /global and each coin’s 30-day history.',
  };
}

export function tipFearGreed(m: CryptoMarket): TipContent {
  const fg = m.fear_greed;
  return {
    title: 'Fear & Greed index',
    tone: fg === null ? 'muted' : fg.value >= 56 ? 'up' : fg.value <= 44 ? 'down' : 'muted',
    what: 'A 0–100 mood score for crypto, built from price swings, momentum, social media and bitcoin dominance. Updated once a day.',
    visual: { kind: 'scale', min: 0, max: 100, value: fg?.value ?? null, mark: fg ? String(fg.value) : undefined,
      zones: FEAR_GREED_ZONES.map((z) => ({ to: z.to, label: z.label, color: z.color })) },
    now: fg === null ? 'Unknown: alternative.me has not answered.' : `${fg.value} · ${fg.label ?? ''}${fg.week_ago === null ? '' : `. A week ago: ${fg.week_ago}`}.`,
    why: 'Extreme greed often comes before pullbacks, extreme fear before bounces. A mood, not a signal.',
    source: 'alternative.me.',
  };
}

export function tipLiquidations(note: string | null): TipContent {
  return {
    title: 'Liquidations · 24 h',
    tone: 'muted',
    what: 'Forced exits: when a leveraged bet loses too much, the exchange closes it for the trader. Longs forced out push the price down; shorts forced out push it up.',
    visual: { kind: 'flow', steps: ['Price dips', 'Longs run out of margin', 'Exchange sells them', 'Price dips more'], note: 'The cascade behind sudden wicks.' },
    now: 'Not known on this desk.',
    why: 'Big liquidation waves mark the moments a move ran out of fuel.',
    source: note ?? 'No free source reports liquidations.',
  };
}

export function tipWhy(c: CryptoCoin): TipContent {
  const kind = c.why?.kind ?? null;
  const items = [
    { label: 'Catalyst', color: COLORS.up, text: 'Something happened: ETF flows, an upgrade, a listing.', active: kind === 'catalyst' },
    { label: 'Negative', color: COLORS.down, text: 'A hack, a lawsuit, a delisting, new supply.', active: kind === 'negative' },
    { label: 'News', color: COLORS.accent, text: 'About the coin, but not a clear cause.', active: kind === 'news' },
    { label: 'Noise', color: COLORS.muted, text: 'The price talking about itself: "why is X up", predictions.', active: kind === 'noise' },
  ];
  return {
    title: `Why ${c.symbol} is moving`,
    tone: kind === 'catalyst' ? 'up' : kind === 'negative' ? 'down' : 'muted',
    what: 'The headline that best explains the move in the last 24 hours, read by Nova’s rules (no AI, no guessing).',
    visual: { kind: 'tags', items },
    now: c.why ? `“${c.why.title}”${c.why.source ? ` · ${c.why.source}` : ''}` : c.news_checked ? 'No news found in the last 24 hours: the move may be the market, not the coin.' : 'Unknown: no news source has answered yet.',
    why: 'A move with a real catalyst tends to hold; a move on noise often fades.',
    source: 'Alpaca news (Benzinga), last 24 hours.',
  };
}

export function tipTrade(c: CryptoCoin): TipContent {
  if (c.etf && c.ibkr?.listed) {
    return {
      title: `How to trade ${c.symbol}`,
      tone: 'up',
      what: `Two ways: buy the coin itself at IBKR, or trade ${c.etf}, its ETF, in Nova’s Trader during stock hours (04:00–20:00 ET).`,
      visual: { kind: 'flow', steps: ['Nova Trader', c.etf, `holds ${c.symbol}`], note: `Or IBKR’s app → ${c.ibkr.venue ?? 'crypto venue'} → ${c.symbol} (needs crypto permission).` },
      why: 'Nova places no crypto orders yet: the ETF is the way to trade it from this desk.',
      source: 'IBKR’s own answer to "do you list this coin?"',
    };
  }
  return tipSpot(c);
}

export function tipSpot(c: CryptoCoin): TipContent {
  if (c.ibkr === null) {
    return { title: `Can you trade ${c.symbol}?`, tone: 'muted', what: 'Nova asks IBKR whether it lists each coin once it is connected.', now: 'Not asked yet: IBKR is not connected.' };
  }
  if (!c.ibkr.listed && !c.etf) {
    return { title: `${c.symbol}: watch only`, tone: 'muted', what: `IBKR does not list ${c.symbol} and no ${c.symbol} ETF trades on this desk.`, why: 'Watch it for the mood of the market; trade the coins and stocks you can reach.' };
  }
  return {
    title: `${c.symbol} on IBKR`,
    tone: 'accent',
    what: `IBKR lists ${c.symbol} on ${c.ibkr.venue ?? 'its crypto venue'}: you can buy the coin itself in IBKR’s app or TWS. It needs crypto permission on your account.`,
    visual: { kind: 'flow', steps: ['You', 'IBKR app / TWS', c.ibkr.venue ?? 'crypto venue', c.symbol] },
    why: 'Nova places no crypto orders yet: this chip says where it can be bought, not that Nova buys it.',
    source: 'IBKR’s own answer to "do you list this coin?"',
  };
}

export function tipEtf(c: CryptoCoin): TipContent {
  return {
    title: `${c.etf}: ${c.symbol} as a stock`,
    tone: 'up',
    what: `${c.etf} is a US ETF that holds ${c.name}. It trades like a stock, so you can trade it in Nova’s Trader, 04:00–20:00 ET on weekdays.`,
    visual: { kind: 'flow', steps: ['Nova Trader', c.etf ?? '', `holds ${c.symbol}`] },
    why: `Click to open ${c.etf} in the Trader.`,
  };
}

export function tipChartLevel(kind: 'high' | 'last' | 'open', data: CryptoCandles, dayOpenEt: string): TipContent {
  const last = data.last;
  const lv = data.levels;
  if (kind === 'high') {
    const gap = last !== null && lv.high_24h ? ((lv.high_24h / last - 1) * 100) : null;
    return { title: '24-hour high', tone: 'muted', what: `The highest trade in the last 24 hours on Coinbase ${data.symbol}-USD.`,
      now: `${level(lv.high_24h)}${gap === null ? '' : `, ${Math.abs(gap).toFixed(2)}% above the last price`}.`,
      why: 'A break above the day’s high often pulls in breakout buyers; a failure under it can mark the top.' };
  }
  if (kind === 'open') {
    const vs = last !== null && lv.day_open ? (last / lv.day_open - 1) * 100 : null;
    return { title: 'The crypto day’s open', tone: 'accent',
      what: `Where the crypto day began: 00:00 UTC, ${dayOpenEt} ET today. Daily candles and "24h" numbers on most sites start here.`,
      now: `${level(lv.day_open)}${vs === null ? '' : `: the price is ${pct(vs)} from it`}.`,
      why: 'Above the day’s open, the day reads green to most traders; below it, red.' };
  }
  return { title: `Last trade · ${data.symbol}`, tone: (data.change_24h_pct ?? 0) >= 0 ? 'up' : 'down',
    what: `The latest trade on Coinbase’s ${data.symbol}-USD market.`, now: `${level(last)}, ${pct(data.change_24h_pct)} in 24 hours.`,
    source: 'Coinbase Exchange candles.' };
}

export function tipStockClose(data: CryptoCandles): TipContent {
  const sc = data.levels.stock_close;
  const since = sc && data.last !== null ? (data.last / sc.price - 1) * 100 : null;
  return {
    title: 'US stock close · 16:00 ET',
    tone: 'warn',
    what: `${data.symbol}’s price when US stocks last closed. What it does after this is what crypto stocks catch up to at the next open.`,
    visual: sc && data.last !== null ? { kind: 'formula', parts: [
      { label: 'now', value: level(data.last) }, { label: 'at 16:00', value: level(sc.price) },
      { label: 'since', value: pct(since), tone: since !== null && since >= 0 ? 'up' : 'down' },
    ], ops: ['vs', '='] } : undefined,
    why: 'Premarket gaps in MARA, COIN and MSTR usually follow this number.',
  };
}

export function tipUsBand(): TipContent {
  return { title: 'US stocks open · 09:30–16:00 ET', tone: 'up',
    what: 'The hours the US stock market is open. Bitcoin often moves hardest here, in step with the Nasdaq.',
    why: 'A crypto move outside these hours shows up in crypto stocks at the next open.' };
}

export function tipEthBtc(m: CryptoMarket): TipContent {
  const ch = m.eth_btc_change_24h_pct;
  return { title: 'ETH/BTC', tone: (ch ?? 0) >= 0 ? 'up' : 'down',
    what: 'Ether’s price measured in bitcoin instead of dollars.',
    now: m.eth_btc === null ? 'Unknown.' : `${m.eth_btc.toFixed(5)}, ${pct(ch, 1)} today: ${(ch ?? 0) >= 0 ? 'ether is beating bitcoin' : 'bitcoin is beating ether'}.`,
    why: 'A rising ETH/BTC usually means traders are reaching for more risk.', source: 'CoinGecko prices.' };
}

export function tipCorr(m: CryptoMarket): TipContent {
  const c = m.btc_qqq_corr_30d;
  return { title: 'Bitcoin vs the Nasdaq 100', tone: 'accent',
    what: 'How closely bitcoin’s daily moves followed the Nasdaq 100 (QQQ) over the last 30 trading days: 1 = in lockstep, 0 = unrelated.',
    visual: { kind: 'scale', min: -1, max: 1, value: c, mark: c === null ? undefined : c.toFixed(2), zones: [
      { to: 0, label: 'Opposite', color: COLORS.down }, { to: 0.3, label: 'Unrelated', color: COLORS.muted },
      { to: 0.6, label: 'Loosely', color: COLORS.accent }, { to: 1, label: 'Together', color: COLORS.up },
    ] },
    now: c === null ? 'Unknown until IBKR and Coinbase have answered.' : c >= 0.6 ? 'Bitcoin has been trading like a tech stock.' : c >= 0.3 ? 'Loosely tied to tech stocks.' : 'Moving on its own lately.',
    why: 'When they move together, a Nasdaq selloff drags crypto down with it.',
    source: 'Coinbase 16:00 ET prices and IBKR’s QQQ closes.' };
}

export function tipSource(s: SourceStatus | undefined, label: string, now: number): TipContent {
  const age = s?.at ? Math.max(0, Math.round(now - s.at)) : null;
  return {
    title: 'Where these numbers come from',
    tone: s?.ok === false ? 'warn' : s?.ok ? 'up' : 'muted',
    what: `${label}. Public data, read only while this page is open; Nova never trades on it.`,
    now: !s || s.ok === null ? 'Not asked yet.' : s.ok ? `Answered ${age === null ? 'recently' : age < 60 ? `${age} s ago` : `${Math.round(age / 60)} min ago`}.` : `Failing: ${s.error ?? 'no answer'}. Its numbers show as — until it answers.`,
  };
}
