/**
 * Session chip beside the wordmark: PREMARKET (amber) / OPEN (green) /
 * AFTER HOURS / CLOSED (muted), from the client's Eastern clock. Ticks with
 * the ET clock and re-renders only when the session changes.
 */
import { useEffect, useState } from 'react';
import { STOCK_VIEW_CLOCK_TICK_MS } from '../constants';
import { sessionChipView } from './globalBarSession';

export function GlobalBarSessionChip() {
  const [view, setView] = useState(() => sessionChipView());

  useEffect(() => {
    const id = window.setInterval(() => {
      setView((prev) => {
        const next = sessionChipView();
        return next.kind === prev.kind ? prev : next;
      });
    }, STOCK_VIEW_CLOCK_TICK_MS);
    return () => window.clearInterval(id);
  }, []);

  return (
    <span
      className={`global-app-bar__session global-app-bar__session--${view.kind}`}
      data-testid="global-bar-session"
      data-session={view.kind}
      title={view.title}
    >
      {view.label}
    </span>
  );
}
