/** Five Pillars pass/fail chips (shared by Watchlist tab + ticker side panel). */
import type { WatchlistEntry } from './types';

export function PillarChips({
  pillars,
}: {
  pillars: WatchlistEntry['five_pillars']['pillars'];
}) {
  return (
    <span className="pillar-chip-row">
      {pillars.map(p => (
        <span
          key={p.name}
          className={`pillar-chip ${p.passed ? 'pillar-pass' : 'pillar-fail'}`}
          title={p.detail}
        >
          {p.passed ? '\u2713' : '\u2717'} {p.name.replace('_', ' ')}
        </span>
      ))}
    </span>
  );
}
