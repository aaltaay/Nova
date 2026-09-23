/** Watchlist pillars / scores strip for the open ticker. */
import { TickerWatchlistStrip } from '../components/TickerWatchlistStrip';
import type { WatchlistEntry } from '../strategy/types';

interface Props {
  entry?: WatchlistEntry | null;
  /** The symbol on screen: graded on demand when the watchlist does not rank it. */
  symbol?: string | null;
  rank?: number | null;
}

export function WatchlistStripPanel({ entry = null, symbol = null, rank = null }: Props) {
  return (
    <div className="nova-module nova-module--watchlist-strip" data-module="watchlist-strip">
      <TickerWatchlistStrip entry={entry} symbol={symbol} rank={rank} />
    </div>
  );
}
