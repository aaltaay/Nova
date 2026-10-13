/**
 * The followed traders' toasts: "CHERIF opened LONG JZ @ 1.55" on any Nova page, mounted once with the app bar (the
 * main desk window, like the hot list's toasts, so two windows never announce one trade twice). Only while the
 * backend has a feed configured and Alerts are on; it reads the feed without prices (`quotes=0`), so it holds no
 * IBKR line. The first answer raises nothing. A toast leaves after FOLLOWED_TOAST_TTL_MS unless hovered; Proof opens
 * the Following page on that trade. Nothing here places or stages an order.
 */
import { useEffect, useRef, useState } from 'react';
import { setNavPage } from '../workspace';
import {
  FOLLOWED_TOAST_MAX,
  FOLLOWED_TOAST_POLL_MS,
  FOLLOWED_TOAST_TTL_MS,
  FT_PROOF,
  FT_TITLE,
  FT_TOAST_DISMISS,
  FT_TOAST_REGION,
} from './constants';
import { useFollowedTradersEnabled } from './enabledStore';
import { requestFollowedProof, useFollowedAlerts } from './followedStores';
import { etTime, price } from './format';
import { Face } from './parts';
import { tradeToasts, type TradeToast } from './toastModel';
import type { FollowedDay } from './types';
import { useFollowedDay } from './useFollowedDay';
import './followed.css';

function Toast({ toast, onDismiss, onProof }: { toast: TradeToast; onDismiss: () => void; onProof: () => void }) {
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
      onBlur={() => setHeld(false)} data-testid={`ft-toast-${toast.key}`}>
      <Face path={toast.face} name={toast.trader} />
      <div className="ft-toast__body">
        <span className="ft-strong">
          {toast.trader} {toast.verb} <span className={`ft-side-text ft-side-text--${toast.side}`}>{toast.side.toUpperCase()}</span>{' '}
          {toast.symbol}{toast.price !== null ? ` @ ${price(toast.price)}` : ''}
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
  const [toasts, setToasts] = useState<TradeToast[]>([]);

  useEffect(() => {
    if (!active) prev.current = null; // switched back on: what happened meanwhile is not news
  }, [active]);

  useEffect(() => {
    if (!active || !data) return;
    const fresh = tradeToasts(prev.current, data);
    prev.current = data;
    if (fresh.length) setToasts((list) => [...list, ...fresh.filter((f) => !list.some((t) => t.key === f.key))].slice(-FOLLOWED_TOAST_MAX));
  }, [data, active]);

  if (toasts.length === 0) return null;
  const dismiss = (key: string) => setToasts((list) => list.filter((t) => t.key !== key));
  return (
    <div className="ft-toasts" role="region" aria-label={FT_TOAST_REGION} data-testid="ft-toasts">
      {toasts.map((t) => (
        <Toast key={t.key} toast={t} onDismiss={() => dismiss(t.key)} onProof={() => {
          onOpenPage?.();
          setNavPage('followed');
          requestFollowedProof({ date: t.date, tradeId: t.tradeId });
          dismiss(t.key);
        }} />
      ))}
    </div>
  );
}
