/**
 * The followed traders' toasts: "CHERIF opened LONG JZ @ 1.55" on any Nova page, mounted once with the app bar (the
 * main desk window, like the hot list's toasts, so two windows never announce one trade twice). Only while the
 * backend has a feed configured and Alerts are on; it reads the feed without prices (`quotes=0`), so it holds no
 * IBKR line. The first answer raises nothing. A toast leaves after FOLLOWED_TOAST_TTL_MS unless hovered; a click
 * anywhere on it opens the TraderTV LIVE page on today, and Proof opens that page on the trade. Nothing here places or stages an order.
 */
import { useEffect, useRef, useState } from 'react';
import { tipProps } from '../ux/hoverTip';
import { TickerLink } from '../components/TickerLink';
import { setNavPage } from '../workspace';
import {
  FOLLOWED_TOAST_MAX,
  FOLLOWED_TOAST_POLL_MS,
  FOLLOWED_TOAST_TTL_MS,
  FT_PROOF,
  FT_TICKER_CHECK,
  FT_TITLE,
  FT_TOAST_DISMISS,
  FT_TOAST_OPEN,
  FT_TOAST_REGION,
} from './constants';
import { useFollowedTradersEnabled } from './enabledStore';
import { requestFollowedProof, requestFollowedToday, useFollowedAlerts } from './followedStores';
import { etTime, price } from './format';
import { Face } from './parts';
import { toastStep, type TradeToast } from './toastModel';
import type { FollowedDay } from './types';
import { useFollowedDay } from './useFollowedDay';
import './followed.css';

interface ToastProps { toast: TradeToast; onDismiss: () => void; onOpen: () => void; onProof: () => void }

function Toast({ toast, onDismiss, onOpen, onProof }: ToastProps) {
  const [held, setHeld] = useState(false);
  // The parent re-renders on every poll; the timer must not restart with it.
  const dismissRef = useRef(onDismiss);
  dismissRef.current = onDismiss;
  useEffect(() => {
    if (held) return undefined;
    const timer = window.setTimeout(() => dismissRef.current(), FOLLOWED_TOAST_TTL_MS);
    return () => window.clearTimeout(timer);
  }, [held]);
  return (
    <div className={`ft-toast ft-toast--${toast.verb === 'closed' ? 'close' : 'open'}`} role="status"
      onMouseEnter={() => setHeld(true)} onMouseLeave={() => setHeld(false)} onFocus={() => setHeld(true)}
      onBlur={() => setHeld(false)} data-testid={`ft-toast-${toast.key}`}
      // A click anywhere opens the page; each button answers its own click (the face is the keyboard's way in).
      onClick={(e) => { if (!(e.target as HTMLElement).closest('button')) onOpen(); }}>
      <button type="button" className="ft-toast__open" aria-label={FT_TOAST_OPEN} onClick={onOpen}>
        <Face path={toast.face} name={toast.trader} />
      </button>
      <div className="ft-toast__body">
        <span className="ft-strong">
          {toast.trader} {toast.verb} <span className={`ft-side-text ft-side-text--${toast.side}`}>{toast.side.toUpperCase()}</span>{' '}
          <TickerLink symbol={toast.symbol} look="own" />{toast.price !== null ? ` @ ${price(toast.price)}` : ''}
          {toast.check && <span className="ft-note ft-note--warn ft-ticker-mark" {...tipProps(toast.check)}>{FT_TICKER_CHECK}</span>}
        </span>
        <span className="ft-small ft-muted">{etTime(toast.ts)} ET · {FT_TITLE}</span>
      </div>
      <button type="button" className="ft-link" onClick={onProof}>{FT_PROOF}</button>
      <button type="button" className="ft-toast__x" aria-label={FT_TOAST_DISMISS} onClick={onDismiss}>×</button>
    </div>
  );
}

export function FollowedToasts({ onOpenPage }: { onOpenPage?: () => void }) {
  const enabled = useFollowedTradersEnabled();
  const alertsOn = useFollowedAlerts();
  const active = enabled && alertsOn;
  const { data } = useFollowedDay(null, { quotes: false, everyMs: FOLLOWED_TOAST_POLL_MS, enabled: active });
  const prev = useRef<FollowedDay | null>(null);
  const held = useRef<ReadonlySet<string>>(new Set()); // trades held back while their ticker is checked
  const [toasts, setToasts] = useState<TradeToast[]>([]);

  useEffect(() => {
    if (!active) { // switched back on: what happened meanwhile is not news
      prev.current = null;
      held.current = new Set();
    }
  }, [active]);

  useEffect(() => {
    if (!active || !data) return;
    const step = toastStep(prev.current, data, held.current);
    const fresh = step.toasts;
    prev.current = data;
    held.current = step.held;
    if (fresh.length) setToasts((list) => [...list, ...fresh.filter((f) => !list.some((t) => t.key === f.key))].slice(-FOLLOWED_TOAST_MAX));
  }, [data, active]);

  if (toasts.length === 0) return null;
  const dismiss = (key: string) => setToasts((list) => list.filter((t) => t.key !== key));
  const openPage = () => {
    onOpenPage?.();
    setNavPage('followed');
  };
  return (
    <div className="ft-toasts" role="region" aria-label={FT_TOAST_REGION} data-testid="ft-toasts">
      {toasts.map((t) => (
        <Toast key={t.key} toast={t} onDismiss={() => dismiss(t.key)}
          onOpen={() => {
            openPage();
            requestFollowedToday();
            dismiss(t.key);
          }}
          onProof={() => {
            openPage();
            requestFollowedProof({ date: t.date, tradeId: t.tradeId });
            dismiss(t.key);
          }} />
      ))}
    </div>
  );
}
