/**
 * "Most traded" (ADR 066, PNG v1): the stocks the most members traded in the period -- the members who sold on the
 * left, who bought on the right, each with their faces -- and the stock's move over the period from IBKR's daily
 * bars (the desk's one price source). Click a stock for everyone who traded it.
 */
import { useMemo } from 'react';
import { TickerLink } from '../components/TickerLink';
import { usePeriodMoves } from './api';
import { periodLabel, PERIODS } from './constants';
import { FaceStack } from './Face';
import { pct } from './format';
import { Seg } from './Seg';
import type { Member, Period, Traded } from './types';

const TILE_COLORS = ['#0a84ff', '#15803d', '#b45309', '#4338ca', '#d9480f', '#0e7490', '#7c3aed', '#3a3a3c'];

function tileColor(ticker: string): string {
  let h = 0;
  for (const c of ticker) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return TILE_COLORS[h % TILE_COLORS.length];
}

export function MostTraded({ rows, period, year, from, byBio, onPeriod, onTicker, onOpenTrader }: {
  rows: Traded[];
  period: Period;
  year: number;
  from: string;
  byBio: Map<string, Member>;
  onPeriod: (p: Period) => void;
  onTicker: (ticker: string) => void;
  onOpenTrader: (symbol: string) => void;
}) {
  const tickers = useMemo(() => rows.map((r) => r.ticker), [rows]);
  const moves = usePeriodMoves(tickers, from);
  const top = Math.max(1, ...rows.map((r) => Math.max(r.buyers.length, r.sellers.length)));
  const faces = (bios: string[]) => bios.map((b) => byBio.get(b) ?? null);
  return (
    <section className="cg-card cg-traded" data-testid="congress-most-traded">
      <div className="cg-card__head">
        <h3 className="cg-card__title">Most traded</h3>
        <span className="cg-muted cg-small">members who sold · members who bought</span>
        <Seg value={period} options={PERIODS} label={(p) => periodLabel(p, year)} onPick={onPeriod} testId="congress-traded-period" />
      </div>
      <div className="cg-mt cg-mt--head">
        <span>Stock</span><span className="is-down">Sold</span><span /><span className="is-up">Bought</span>
        <span className="cg-mt__move">Move</span>
      </div>
      {rows.length === 0 ? <p className="cg-muted cg-empty">No stock trades reported in this period.</p> : null}
      {rows.map((r) => {
        const m = moves[r.ticker];
        return (
          <div key={r.ticker} className="cg-mt is-clickable" role="button" tabIndex={0} onClick={() => onTicker(r.ticker)}
            onKeyDown={(e) => { if (e.key === 'Enter') onTicker(r.ticker); }} data-testid={`congress-traded-${r.ticker}`}>
            <span className="cg-mt__sym">
              <span className="cg-tile" style={{ background: tileColor(r.ticker) }}>{r.ticker.slice(0, 5)}</span>
              <span><b><TickerLink symbol={r.ticker} onOpen={onOpenTrader} look="own" /></b><small>{r.asset}</small></span>
            </span>
            <span className="cg-mt__side is-left">
              <FaceStack members={faces(r.sellers)} ring="#ff453a" />
              <span className="cg-mt__n">{r.sellers.length}</span>
              <span className="cg-bar cg-bar--sell" style={{ width: `${Math.max(4, (100 * r.sellers.length) / top)}%` }} />
            </span>
            <span className="cg-mt__axis" />
            <span className="cg-mt__side">
              <span className="cg-bar cg-bar--buy" style={{ width: `${Math.max(4, (100 * r.buyers.length) / top)}%` }} />
              <span className="cg-mt__n">{r.buyers.length}</span>
              <FaceStack members={faces(r.buyers)} ring="#30d158" />
            </span>
            <span className="cg-mt__move" title={`${periodLabel(period, year)} move from IBKR's daily bars`}>
              {m?.state === 'ok' ? <b className={(m.pct ?? 0) >= 0 ? 'is-up' : 'is-down'}>{pct(m.pct)}</b>
                : <b className="cg-muted">{m?.state === 'none' ? 'no bars' : '…'}</b>}
              <small>IBKR</small>
            </span>
          </div>
        );
      })}
    </section>
  );
}
