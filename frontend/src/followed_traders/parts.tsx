/**
 * Small pieces the Followed traders page repeats: the side chip, a ticker that opens the Trader, a trader's photo, a
 * record, a P/L, a result.
 */
import { createContext, useContext } from 'react';
import { tipProps } from '../ux/hoverTip';
import { FT_OPEN_IN_TRADER, FT_RESULT_WORDS, FT_UNSCORED_TIP } from './constants';
import { FeedImage } from './FeedImage';
import { plPct, plPerShare, plTone } from './format';
import type { FollowedRecord, FollowedTrade, TradeResult } from './types';

export function SideChip({ side }: { side: 'long' | 'short' }) {
  return <span className={`ft-side ft-side--${side}`}>{side.toUpperCase()}</span>;
}

/** The desk's "open this symbol in the Trader", provided by the page; null where there is no Trader to open. */
export const OpenTraderContext = createContext<((symbol: string) => void) | null>(null);

/** A trade's ticker: clicking it opens the stock in the Trader. Plain text when the desk gave the page no Trader. */
export function Ticker({ symbol, className }: { symbol: string; className: string }) {
  const open = useContext(OpenTraderContext);
  if (!open) return <span className={className}>{symbol}</span>;
  return (
    <button type="button" className={`${className} ft-ticker-link`} onClick={() => open(symbol)}
      aria-label={`${FT_OPEN_IN_TRADER}: ${symbol}`} {...tipProps(FT_OPEN_IN_TRADER)}>
      {symbol}
    </button>
  );
}

/** The trader's photo from the stream, or their name's first letter when the feed has none. */
export function Face({ path, name, size = 'md' }: { path: string | null; name: string; size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl' }) {
  if (!path) {
    return <span className={`ft-face ft-face--${size} ft-face--letter`} aria-hidden="true">{name.slice(0, 1)}</span>;
  }
  return <FeedImage path={path} alt={`${name}, as shown on the stream`} className={`ft-face ft-face--${size}`} />;
}

export function recordText(r: FollowedRecord): string {
  const parts = [`${r.wins}W / ${r.losses}L`];
  if (r.open) parts.push(`${r.open} open`);
  parts.push(r.win_rate === null ? 'Win rate —' : `Win rate ${r.win_rate}%`);
  return parts.join(' · ');
}

export function recordExtras(r: FollowedRecord): string | null {
  const parts = [];
  if (r.scratches) parts.push(`${r.scratches} scratch${r.scratches === 1 ? '' : 'es'}`);
  if (r.unscored) parts.push(`${r.unscored} unscored`);
  return parts.length ? parts.join(' · ') : null;
}

export function RecordChips({ record, testId }: { record: FollowedRecord | null; testId?: string }) {
  if (!record) return <span className="ft-pill-chip ft-muted" data-testid={testId}>—</span>;
  const extras = recordExtras(record);
  return (
    <span className="ft-record" data-testid={testId}>
      <span className="ft-pill-chip"><b>{recordText(record)}</b></span>
      {extras && <span className="ft-pill-chip ft-muted" {...tipProps(FT_UNSCORED_TIP)}>{extras}</span>}
    </span>
  );
}

/** P/L per share and %, stacked, or on one line (`inline`) in a closed trade's row. */
export function PlCell({ trade, inline = false, big = false }: { trade: FollowedTrade; inline?: boolean; big?: boolean }) {
  const tone = plTone(trade.pl);
  return (
    <span className={`ft-pl ft-pl--${tone}${inline ? ' ft-pl--inline' : ''}${big ? ' ft-pl--big' : ''}`}>
      <span className="ft-mono ft-pl__share">{plPerShare(trade.pl, trade.entry.avg_price)}</span>
      {trade.pl && <span className="ft-mono ft-pl__pct">{plPct(trade.pl)}</span>}
    </span>
  );
}

const RESULT_TIPS: Partial<Record<TradeResult, string>> = {
  scratch: 'P/L exactly 0: left out of the win rate',
  unscored: FT_UNSCORED_TIP,
};

/** A closed trade's result in words: WIN, LOSS, SCRATCH or UNSCORED (the row's stripe is its colour). */
export function ResultWord({ result }: { result: TradeResult | null }) {
  const r = result ?? 'unscored';
  return <span className={`ft-result-word ft-result-word--${r}`} {...tipProps(RESULT_TIPS[r] ?? null)}>{FT_RESULT_WORDS[r]}</span>;
}
