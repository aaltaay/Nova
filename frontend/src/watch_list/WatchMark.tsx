/** The eye beside a watched ticker; nothing for a symbol that is not watched. */
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
