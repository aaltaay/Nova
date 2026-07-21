/** Live Eastern market clock + session chip for Stock View header. */
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
      className={`sv-header__clock sv-header__clock--${snap.sessionKind}`}
      dateTime={new Date().toISOString()}
      data-testid="stock-view-market-clock"
      data-session={snap.sessionKind}
      title={`US equity session · ${snap.sessionLabel}`}
      aria-label={`Eastern time ${snap.timeLabel}, session ${snap.sessionLabel}`}
    >
      <span className="sv-header__clock-time">{snap.timeLabel}</span>
      <span className="sv-header__clock-session">{snap.sessionLabel}</span>
    </time>
  );
}
