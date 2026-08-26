/** Live Eastern clock for the global bar -- time only; session is the mode badge. */
import { useEffect, useState } from 'react';
import { STOCK_VIEW_CLOCK_TICK_MS } from '../constants';
import { marketClockSnapshot } from './marketClock';

export function StockViewMarketClock() {
  const [snap, setSnap] = useState(() => marketClockSnapshot());

  useEffect(() => {
    const id = window.setInterval(
      () => setSnap(marketClockSnapshot()),
      STOCK_VIEW_CLOCK_TICK_MS,
    );
    return () => window.clearInterval(id);
  }, []);

  return (
    <time
      className={`header-market-clock header-market-clock--${snap.sessionKind}`}
      dateTime={new Date().toISOString()}
      data-testid="header-market-clock"
      data-session={snap.sessionKind}
      title={`US equity session · ${snap.sessionLabel}`}
      aria-label={`Eastern time ${snap.timeLabel}`}
    >
      {snap.timeLabel}
    </time>
  );
}
