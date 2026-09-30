/** The Cryptos page's coins table (ADR 040): the listed coins, sortable and filterable, every cell explained. */
import { useMemo, useState } from 'react';
import { COIN_GROUPS, COIN_SORTS, VOLUME_HOT_X, type CoinGroup, type CoinSort } from './constants';
import { funding, mult, pct, price, tone, usd } from './format';
import { Card, Spark } from './parts';
import {
  COIN_ABOUT,
  fundingWords,
  tipCap,
  tipChanges,
  tipCoinPrice,
  tipEtf,
  tipFunding,
  tipSpark,
  tipSpot,
  tipVolume,
  tipWhy,
} from './tips/glossaryMarket';
import { useTip, type TipContent } from './tips/TipHost';
import type { CryptoBoard, CryptoCoin } from './types';

const GROUP_LABEL: Record<string, string> = {
  major: 'a major', layer1: 'a Layer 1', meme: 'a meme coin', payments: 'a payments coin', defi: 'DeFi plumbing',
};

function tipCoin(c: CryptoCoin): TipContent {
  return {
    title: `${c.name} · ${c.symbol}${c.rank ? ` #${c.rank}` : ''}`,
    tone: (c.change_24h_pct ?? 0) >= 0 ? 'up' : 'down',
    what: COIN_ABOUT[c.symbol] ?? c.name,
    visual: c.spark_7d.length > 1 ? { kind: 'spark', values: c.spark_7d, up: (c.change_7d_pct ?? 0) >= 0, startLabel: '7 days ago', endLabel: 'now' } : undefined,
    now: `${c.groups.map((g) => GROUP_LABEL[g] ?? g).join(', ')}${c.from_ath_pct === null ? '' : ` · ${Math.abs(c.from_ath_pct).toFixed(0)}% under its all-time high`}.`,
    why: c.chart ? 'Click the row to put it on the chart.' : 'Coinbase has no USD market for it, so it has no chart here.',
  };
}

function sortCoins(coins: CryptoCoin[], sort: CoinSort, group: CoinGroup): CryptoCoin[] {
  const inGroup = group === 'all' ? coins : coins.filter((c) => c.groups.includes(group));
  const list = sort === 'tradeable' ? inGroup.filter((c) => c.ibkr?.listed || c.etf) : [...inGroup];
  const key = (c: CryptoCoin): number => {
    if (sort === 'movers') return Math.abs(c.change_24h_pct ?? -1);
    if (sort === 'volume') return c.volume_x_30d ?? -1;
    return c.market_cap_usd ?? -1;
  };
  return list.sort((a, b) => key(b) - key(a));
}

function TradeCell({ c, onOpenTrader }: { c: CryptoCoin; onOpenTrader: (s: string) => void }) {
  const tip = useTip();
  if (c.ibkr === null && !c.etf) {
    return <span className="cx-muted" {...tip(() => tipSpot(c))}>Not checked</span>;
  }
  if (!c.ibkr?.listed && !c.etf) {
    return <span className="cx-muted" {...tip(() => tipSpot(c))}>Watch only</span>;
  }
  return (
    <span className="cx-trade">
      {c.ibkr?.listed ? <span className="cx-chip cx-chip--spot" tabIndex={0} {...tip(() => tipSpot(c))}>Spot</span> : null}
      {c.etf ? (
        <button type="button" className="cx-chip cx-chip--etf" onClick={(e) => { e.stopPropagation(); onOpenTrader(c.etf as string); }}
          {...tip(() => tipEtf(c))}>{c.etf}</button>
      ) : null}
    </span>
  );
}

function WhyCell({ c }: { c: CryptoCoin }) {
  const tip = useTip();
  if (!c.why) {
    return <span className="cx-muted" {...tip(() => tipWhy(c))}>{c.news_checked ? 'No news found' : 'Not checked yet'}</span>;
  }
  const label = { catalyst: 'Catalyst', negative: 'Negative', noise: 'Noise', news: 'News' }[c.why.kind];
  return (
    <span className="cx-why" {...tip(() => tipWhy(c))}>
      <span className={`cx-tag cx-tag--${c.why.kind}`}>{label}</span>
      <span className="cx-why__text">{c.why.title}</span>
    </span>
  );
}

export function CoinsCard({ board, selected, onSelect, onOpenTrader }: {
  board: CryptoBoard;
  selected: string;
  onSelect: (symbol: string) => void;
  onOpenTrader: (symbol: string) => void;
}) {
  const tip = useTip();
  const [sort, setSort] = useState<CoinSort>('cap');
  const [group, setGroup] = useState<CoinGroup>('all');
  const rows = useMemo(() => sortCoins(board.coins, sort, group), [board.coins, sort, group]);
  const groupCount = (g: CoinGroup) => (g === 'all' ? board.coins.length : board.coins.filter((c) => c.groups.includes(g)).length);
  return (
    <Card
      title="Coins"
      className="cx-coins"
      testId="crypto-coins"
      source={{ ids: ['coingecko', 'hyperliquid', 'alpaca'], label: 'Prices: CoinGecko · funding: Hyperliquid · news: Alpaca', sources: board.sources, now: board.clock.now }}
      head={
        <div className="cx-tabs" role="tablist">
          {COIN_SORTS.map((s) => (
            <button key={s.id} type="button" role="tab" aria-selected={sort === s.id} className={`cx-tab${sort === s.id ? ' is-active' : ''}`}
              onClick={() => setSort(s.id)} {...tip(() => ({ title: s.label, what: s.tip }))}>{s.label}</button>
          ))}
          <span className="cx-tabs__sep" />
          {COIN_GROUPS.map((g) => (
            <button key={g.id} type="button" aria-pressed={group === g.id} className={`cx-pill${group === g.id ? ' is-active' : ''}`}
              onClick={() => setGroup(g.id)} {...tip(() => ({ title: g.label, what: g.tip }))}>
              {g.id === 'all' ? `All ${groupCount('all')}` : g.label}
            </button>
          ))}
        </div>
      }
    >
      <div className="cx-table-wrap">
        <table className="cx-table">
          <thead>
            <tr>
              <th className="is-num">#</th>
              <th>Coin</th>
              <th className="is-num">Price</th>
              <th className="is-num">1h</th>
              <th className="is-num">24h</th>
              <th>7 days</th>
              <th className="is-num">Volume 24h</th>
              <th className="is-num">Mkt cap</th>
              <th className="is-num">Funding</th>
              <th>Why it’s moving</th>
              <th>Trade</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c, i) => (
              <tr key={c.symbol} className={`${c.symbol === selected ? 'is-selected' : ''}${c.chart ? ' is-chartable' : ''}`}
                data-testid={`crypto-coin-${c.symbol}`} onClick={() => c.chart && onSelect(c.symbol)}>
                <td className="is-num cx-muted">{c.rank ?? i + 1}</td>
                <td {...tip(() => tipCoin(c))}>
                  <span className="cx-sym">{c.symbol}</span>
                  <span className="cx-name">{c.name}</span>
                </td>
                <td className="is-num cx-strong" {...tip(() => tipCoinPrice(c))}>{price(c.price)}</td>
                <td className={`is-num ${tone(c.change_1h_pct)}`} {...tip(() => tipChanges(c))}>{pct(c.change_1h_pct, 1)}</td>
                <td className={`is-num cx-strong ${tone(c.change_24h_pct)}`} {...tip(() => tipChanges(c))}>{pct(c.change_24h_pct)}</td>
                <td {...tip(() => tipSpark(c))}>
                  <span className="cx-7d">
                    <Spark data={c.spark_7d} w={52} h={18} up={(c.change_7d_pct ?? 0) >= 0} />
                    <span className={tone(c.change_7d_pct)}>{pct(c.change_7d_pct, 1)}</span>
                  </span>
                </td>
                <td className="is-num" {...tip(() => tipVolume(c))}>
                  {usd(c.volume_24h_usd)}{' '}
                  <span className={`cx-x${c.volume_x_30d !== null && c.volume_x_30d >= VOLUME_HOT_X ? ' is-hot' : ''}`}>{mult(c.volume_x_30d)}</span>
                </td>
                <td className="is-num" {...tip(() => tipCap(c))}>{usd(c.market_cap_usd)}</td>
                <td className={`is-num ${fundingClass(c.funding_8h_pct)}`} {...tip(() => tipFunding(c.symbol, c.funding_8h_pct))}>
                  {funding(c.funding_8h_pct)}
                </td>
                <td><WhyCell c={c} /></td>
                <td><TradeCell c={c} onOpenTrader={onOpenTrader} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 ? <p className="cx-empty">No coin fits these filters.</p> : null}
      </div>
      <p className="cx-foot">
        <span className="cx-chip cx-chip--spot">Spot</span> IBKR lists the coin (buy it in IBKR’s app; needs crypto permission) ·
        <span className="cx-chip cx-chip--etf">IBIT</span> its ETF, tradeable in Nova’s Trader 04:00–20:00 ET ·
        Funding over +0.030% per 8h = crowded longs
      </p>
    </Card>
  );
}

function fundingClass(rate: number | null): string {
  const words = fundingWords(rate);
  return rate === null ? 'cx-muted' : words === 'longs are crowded' ? 'is-warn' : words === 'shorts are crowded' ? 'is-cool' : '';
}
