/** The Cryptos page's top tiles (ADR 040): BTC, ETH, the market, dominance, volume, mood, funding, liquidations. */
import type { ReactNode } from 'react';
import { funding, mult, pct, pt, tilePrice, usdFine } from './format';
import { Gauge, Spark } from './parts';
import {
  fundingWords,
  tipCoinPrice,
  tipDominance,
  tipFearGreed,
  tipFunding,
  tipLiquidations,
  tipTotalCap,
  tipTotalVolume,
} from './tips/glossaryMarket';
import { useTip, type TipContent } from './tips/TipHost';
import type { CryptoBoard, CryptoCoin } from './types';

function Tile({ id, label, value, sub, subTone, side, tip }: {
  id: string;
  label: string;
  value: string;
  sub: string;
  subTone?: 'is-up' | 'is-down' | 'is-warn' | '';
  side?: ReactNode;
  tip: () => TipContent;
}) {
  const t = useTip();
  return (
    <div className="cx-kpi" data-testid={`crypto-kpi-${id}`} tabIndex={0} {...t(tip)}>
      <div className="cx-kpi__text">
        <span className="cx-kpi__label">{label}</span>
        <span className={`cx-kpi__value${value === '—' ? ' is-unknown' : ''}`}>{value}</span>
        <span className={`cx-kpi__sub ${subTone ?? ''}`}>{sub}</span>
      </div>
      {side}
    </div>
  );
}

function coinTile(c: CryptoCoin | undefined, id: string, label: string) {
  const ch = c?.change_24h_pct ?? null;
  const last24 = c ? c.spark_7d.slice(-Math.max(2, Math.round(c.spark_7d.length / 7))) : [];
  return {
    id,
    label,
    value: tilePrice(c?.price ?? null),
    sub: ch === null ? 'waiting for CoinGecko' : `${pct(ch)} 24h`,
    subTone: (ch === null ? '' : ch >= 0 ? 'is-up' : 'is-down') as 'is-up' | 'is-down' | '',
    side: <Spark data={last24} w={64} h={34} up={(ch ?? 0) >= 0} />,
    tip: () => (c ? tipCoinPrice(c) : { title: label, what: 'Waiting for CoinGecko.' }),
  };
}

/** The listed coins' combined market value along their 7-day paths (each coin's cap scaled by its own price path). */
export function combinedCap(coins: CryptoCoin[]): number[] {
  const usable = coins.filter((c) => c.market_cap_usd !== null && c.spark_7d.length > 1 && c.spark_7d[c.spark_7d.length - 1] > 0);
  const n = Math.min(...usable.map((c) => c.spark_7d.length));
  if (!usable.length || !Number.isFinite(n)) return [];
  return Array.from({ length: n }, (_, i) =>
    usable.reduce((sum, c) => {
      const path = c.spark_7d.slice(-n);
      return sum + (c.market_cap_usd as number) * (path[i] / path[n - 1]);
    }, 0));
}

export function KpiStrip({ board }: { board: CryptoBoard }) {
  const m = board.market;
  const btc = board.coins.find((c) => c.symbol === 'BTC');
  const eth = board.coins.find((c) => c.symbol === 'ETH');
  const dom = m.btc_dominance_change_24h_pt;
  const fg = m.fear_greed;
  const btcFunding = btc?.funding_8h_pct ?? null;
  const oi = board.leverage.btc_open_interest_usd;
  return (
    <div className="cx-kpis">
      <Tile {...coinTile(btc, 'btc', 'BTC · Bitcoin')} />
      <Tile {...coinTile(eth, 'eth', 'ETH · Ether')} />
      <Tile id="cap" label="Crypto market cap" value={usdFine(m.total_cap_usd)}
        sub={m.total_cap_change_24h_pct === null ? 'waiting for CoinGecko' : `${pct(m.total_cap_change_24h_pct)} 24h`}
        subTone={m.total_cap_change_24h_pct === null ? '' : m.total_cap_change_24h_pct >= 0 ? 'is-up' : 'is-down'}
        side={<Spark data={combinedCap(board.coins).slice(-12)} w={64} h={34} up={(m.total_cap_change_24h_pct ?? 0) >= 0} />}
        tip={() => tipTotalCap(m)} />
      <Tile id="dom" label="BTC dominance" value={m.btc_dominance_pct === null ? '—' : `${m.btc_dominance_pct.toFixed(1)}%`}
        sub={dom === null ? 'change unknown' : `${pt(dom)} · ${dom < 0 ? 'alts leading' : dom > 0 ? 'BTC leading' : 'flat'}`}
        subTone={dom === null ? '' : dom < 0 ? 'is-down' : 'is-up'} tip={() => tipDominance(m)} />
      <Tile id="vol" label="24h volume" value={usdFine(m.total_volume_usd)}
        sub={m.volume_x_30d === null ? 'usual day not known yet' : `${mult(m.volume_x_30d, 2)} its 30-day average`}
        subTone={m.volume_x_30d === null ? '' : m.volume_x_30d >= 1 ? 'is-up' : 'is-down'} tip={() => tipTotalVolume(m)} />
      <Tile id="fng" label="Fear & Greed" value={fg ? String(fg.value) : '—'}
        sub={fg ? `${fg.label ?? ''}${fg.week_ago === null ? '' : `, ${fg.value >= fg.week_ago ? 'up' : 'down'} from ${fg.week_ago}`}` : 'waiting for alternative.me'}
        subTone={fg ? (fg.value >= 56 ? 'is-up' : fg.value <= 44 ? 'is-down' : '') : ''}
        side={<Gauge value={fg?.value ?? null} />} tip={() => tipFearGreed(m)} />
      <Tile id="fund" label="BTC funding · 8h" value={funding(btcFunding)}
        sub={oi === null ? `${fundingWords(btcFunding)}` : `Hyperliquid OI ${usdFine(oi)}`}
        subTone={btcFunding !== null && fundingWords(btcFunding) !== 'calm' ? 'is-warn' : ''}
        tip={() => tipFunding('BTC', btcFunding, oi)} />
      <Tile id="liq" label="Liquidated · 24h" value="—" sub="No free source yet"
        side={<div className="cx-liq is-unknown" aria-hidden><span /></div>}
        tip={() => tipLiquidations(board.leverage.liquidations_note)} />
    </div>
  );
}
