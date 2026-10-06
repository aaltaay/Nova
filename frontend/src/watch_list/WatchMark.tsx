/**
 * The star beside a ticker on today's hot list (ADR 044, amended 2026-10-06): a filled ★ for your star, an
 * outline ☆ for an auto star (the top of the Gainers board); nothing for a ticker that is not on it. It marks
 * watching only -- who trades the stock is its Buy / Sell.
 */
import { WatchEyeIcon } from './WatchEyeIcon';
import { watchMarkTitle } from './watchListConstants';
import { useWatchHow } from './watchListStore';
import './watchList.css';

export function WatchMark({ symbol, className = '' }: { symbol: string; className?: string }) {
  const how = useWatchHow(symbol);
  if (how === null) return null;
  return (
    <span className={`watch-mark-host${className ? ` ${className}` : ''}`} data-testid="watch-mark" data-how={how}
      title={watchMarkTitle(symbol, how)}>
      <WatchEyeIcon className="watch-mark" hollow={how === 'auto'} />
    </span>
  );
}
