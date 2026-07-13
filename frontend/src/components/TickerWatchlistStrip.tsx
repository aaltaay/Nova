/** Watchlist pillars / detail chips / sub-scores / composite for the selected ticker. */
import {
  TICKER_WATCHLIST_STRIP_EMPTY,
  TICKER_WATCHLIST_STRIP_TITLE,
  WATCHLIST_SUBSCORE_LABELS,
  WATCHLIST_SUBSCORE_TOOLTIPS,
} from '../constants';
import { PillarChips } from '../strategy/PillarChips';
import type { WatchlistEntry } from '../strategy/types';

function fmtScore(v: number): string {
  return v.toFixed(0);
}

interface Props {
  entry: WatchlistEntry | null | undefined;
}

export function TickerWatchlistStrip({ entry }: Props) {
  return (
    <section className="cq-watchlist-strip" aria-label={TICKER_WATCHLIST_STRIP_TITLE}>
      <div className="cq-section-title">{TICKER_WATCHLIST_STRIP_TITLE}</div>
      {!entry ? (
        <div className="cq-watchlist-strip-empty">{TICKER_WATCHLIST_STRIP_EMPTY}</div>
      ) : (
        <div className="cq-watchlist-strip-table-wrap">
          <table className="cq-watchlist-strip-table">
            <thead>
              <tr>
                <th title="How many of the 5 Pillars currently pass">Pillars</th>
                <th title="Hover a chip to see why that pillar passed or failed">Detail</th>
                {Object.entries(WATCHLIST_SUBSCORE_LABELS).map(([key, label]) => (
                  <th key={key} title={WATCHLIST_SUBSCORE_TOOLTIPS[key] ?? label}>{label}</th>
                ))}
                <th title="Weighted 0-100 composite of the sub-scores">Score</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <span
                    className={entry.five_pillars.all_pass ? 'positive' : 'na-muted'}
                    title={`${entry.five_pillars.pass_count} of ${entry.five_pillars.total} pillars pass`}
                  >
                    {entry.five_pillars.checkmark}
                  </span>
                </td>
                <td><PillarChips pillars={entry.five_pillars.pillars} /></td>
                {Object.keys(WATCHLIST_SUBSCORE_LABELS).map(key => (
                  <td key={key}>
                    {fmtScore(entry.sub_scores[key as keyof typeof entry.sub_scores])}
                  </td>
                ))}
                <td className="watchlist-composite-cell">{fmtScore(entry.composite_score)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
