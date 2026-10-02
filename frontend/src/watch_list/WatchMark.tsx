/** The star beside a ticker on today's hot list; nothing for one that is not on it. */
import { WatchEyeIcon } from './WatchEyeIcon';
import { watchMarkTitle } from './watchListConstants';
import { useIsWatched } from './watchListStore';
import './watchList.css';

export function WatchMark({ symbol, className = '' }: { symbol: string; className?: string }) {
  const watched = useIsWatched(symbol);
  if (!watched) return null;
  return (
    <span className={`watch-mark-host${className ? ` ${className}` : ''}`} data-testid="watch-mark" title={watchMarkTitle(symbol)}>
      <WatchEyeIcon className="watch-mark" />
    </span>
  );
}
