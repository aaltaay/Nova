/** Watchlist pillars / scores strip for the open ticker. */
import { TickerWatchlistStrip } from '../components/TickerWatchlistStrip';
import type { WatchlistEntry } from '../strategy/types';

interface Props {
  entry?: WatchlistEntry | null;
}

export function WatchlistStripPanel({ entry = null }: Props) {
  return (
    <div className="nova-module nova-module--watchlist-strip" data-module="watchlist-strip">
      <TickerWatchlistStrip entry={entry} />
    </div>
  );
}
