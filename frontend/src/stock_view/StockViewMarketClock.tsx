/** Live Eastern clock for the global bar -- time only; session is the mode badge. */
import { useEffect, useState } from 'react';
import { STOCK_VIEW_CLOCK_TICK_MS } from '../constants';
import { LiveText } from '../ux/LiveText';
import { marketClockSnapshot, type MarketClockSnapshot } from './marketClock';

/** The clock's state: the snapshot and the instant it was read, so a render of the bar changes nothing. */
interface Reading {
  snap: MarketClockSnapshot;
  iso: string;
}

function read(): Reading {
  const now = new Date();
  return { snap: marketClockSnapshot(now), iso: now.toISOString() };
}

export function StockViewMarketClock() {
  const [{ snap, iso }, setReading] = useState(read);

  useEffect(() => {
    const id = window.setInterval(() => setReading(read()), STOCK_VIEW_CLOCK_TICK_MS);
    return () => window.clearInterval(id);
  }, []);

  // The seconds tick in their own layout box (#707): a new second never lays out the page.
  return (
    <time
      className={`header-market-clock header-market-clock--${snap.sessionKind}`}
      dateTime={iso}
      data-testid="header-market-clock"
      data-session={snap.sessionKind}
      title={`US equity session · ${snap.sessionLabel}`}
      aria-label={`Eastern time ${snap.timeLabel}`}
    >
      <LiveText text={snap.timeLabel} />
    </time>
  );
}
