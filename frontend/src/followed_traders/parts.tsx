/** Small pieces the Followed traders page repeats: the side chip, a trader's photo, a record, a P/L, a result. */
import { tipProps } from '../ux/hoverTip';
import { FT_RESULT_LABELS, FT_UNSCORED_TIP } from './constants';
import { FeedImage } from './FeedImage';
import { plPct, plPerShare, plTone } from './format';
import type { FollowedRecord, FollowedTrade, TradeResult } from './types';

export function SideChip({ side }: { side: 'long' | 'short' }) {
  return <span className={`ft-side ft-side--${side}`}>{side.toUpperCase()}</span>;
}

/** The trader's photo from the stream, or their name's first letter when the feed has none. */
export function Face({ path, name, size = 'md' }: { path: string | null; name: string; size?: 'sm' | 'md' | 'lg' }) {
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

export function PlCell({ trade }: { trade: FollowedTrade }) {
  const tone = plTone(trade.pl);
  return (
    <span className={`ft-pl ft-pl--${tone}`}>
      <span className="ft-mono">{plPerShare(trade.pl, trade.entry.avg_price)}</span>
      {trade.pl && <span className="ft-pl__pct">{plPct(trade.pl)}</span>}
    </span>
  );
}

/** Only the results colour cannot say: a scratch and an unscored trade. */
export function ResultChip({ result }: { result: TradeResult | null }) {
  if (result !== 'scratch' && result !== 'unscored') return null;
  const tip = result === 'unscored' ? FT_UNSCORED_TIP : 'P/L exactly 0: left out of the win rate';
  return <span className={`ft-result ft-result--${result}`} {...tipProps(tip)}>{FT_RESULT_LABELS[result]}</span>;
}
