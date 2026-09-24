/**
 * "XYZ hit HOD Momo" toasts for the operator's watch list, mounted once with
 * the app bar (the main desk window, like the setup alert card, so two windows
 * never announce the same alert twice). A toast leaves on its own after
 * WATCH_TOAST_TTL_MS from its newest alert; hovering or focusing it holds it.
 * Nothing here places or stages an order.
 */
import { useEffect, useState, useSyncExternalStore } from 'react';
import { fmtStripClock, subscribeHodMomoLiveAlerts } from '../hod_momo';
import { fmtPct, fmtPrice, fmtRvol, fmtVolume } from '../utils/quoteFormat';
import { WatchEyeIcon } from './WatchEyeIcon';
import {
  WATCH_TOAST_DISMISS,
  WATCH_TOAST_REGION,
  WATCH_TOAST_TTL_MS,
  WATCH_TOAST_UNWATCH,
  watchToastCount,
  watchToastOpen,
  watchToastTitle,
} from './watchListConstants';
import { removeFromWatchList } from './watchListStore';
import {
  dismissWatchToast,
  getWatchToasts,
  noteWatchedHodAlert,
  subscribeWatchToasts,
  type WatchToast,
} from './watchToasts';
import './watchList.css';

/** Price · change · volume · RVOL of the newest alert; an unknown fact is left out, never invented. */
export function watchToastFacts(toast: WatchToast): string {
  const { alert } = toast;
  const facts: string[] = [];
  if (alert.price != null && Number.isFinite(alert.price)) facts.push(fmtPrice(alert.price));
  // Alerts carry percent points; fmtPct takes a fraction.
  if (alert.change_pct != null && Number.isFinite(alert.change_pct)) facts.push(fmtPct(alert.change_pct / 100));
  if (alert.volume != null && Number.isFinite(alert.volume)) facts.push(`Vol ${fmtVolume(alert.volume)}`);
  const rvol = fmtRvol(alert.rvol);
  if (rvol) facts.push(`RVOL ${rvol}`);
  return facts.join(' · ');
}

function WatchToastCard({ toast, onOpenSymbol }: { toast: WatchToast; onOpenSymbol?: (symbol: string) => void }) {
  const [held, setHeld] = useState(false);
  const { symbol } = toast;

  useEffect(() => {
    if (held) return undefined;
    const id = window.setTimeout(() => dismissWatchToast(symbol), WATCH_TOAST_TTL_MS);
    return () => window.clearTimeout(id);
  }, [held, toast.lastAt, symbol]);

  const strategies = toast.strategies.join(' · ');
  const facts = watchToastFacts(toast);
  return (
    <div
      className="watch-toast"
      role="status"
      aria-live="polite"
      data-testid="watch-toast"
      data-symbol={symbol}
      onMouseEnter={() => setHeld(true)}
      onMouseLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)}
      onBlur={() => setHeld(false)}
    >
      <WatchEyeIcon className="watch-toast__eye" />
      <div className="watch-toast__text">
        <div className="watch-toast__head">
          <strong className="watch-toast__title">{watchToastTitle(symbol)}</strong>
          <span className="watch-toast__time">{fmtStripClock(toast.alert)}</span>
        </div>
        {strategies || toast.count > 1 ? (
          <span className="watch-toast__body" data-testid="watch-toast-body">
            {strategies}
            {toast.count > 1 ? <span className="watch-toast__count"> · {watchToastCount(toast.count)}</span> : null}
          </span>
        ) : null}
        {facts ? <span className="watch-toast__facts" data-testid="watch-toast-facts">{facts}</span> : null}
        <div className="watch-toast__actions">
          {onOpenSymbol ? (
            <button
              type="button"
              className="watch-toast__action"
              data-testid="watch-toast-open"
              onClick={() => {
                onOpenSymbol(symbol);
                dismissWatchToast(symbol);
              }}
            >
              {watchToastOpen(symbol)}
            </button>
          ) : null}
          <button
            type="button"
            className="watch-toast__action watch-toast__action--quiet"
            data-testid="watch-toast-unwatch"
            onClick={() => {
              removeFromWatchList(symbol);
              dismissWatchToast(symbol);
            }}
          >
            {WATCH_TOAST_UNWATCH}
          </button>
        </div>
      </div>
      <button
        type="button"
        className="watch-toast__dismiss"
        data-testid="watch-toast-dismiss"
        aria-label={WATCH_TOAST_DISMISS}
        title={WATCH_TOAST_DISMISS}
        onClick={() => dismissWatchToast(symbol)}
      >
        ×
      </button>
    </div>
  );
}

export function WatchHodToasts({ onOpenSymbol }: { onOpenSymbol?: (symbol: string) => void }) {
  const toasts = useSyncExternalStore(subscribeWatchToasts, getWatchToasts, getWatchToasts);
  useEffect(() => subscribeHodMomoLiveAlerts(alert => {
    noteWatchedHodAlert(alert);
  }), []);

  if (toasts.length === 0) return null;
  return (
    <div className="watch-toasts" role="region" aria-label={WATCH_TOAST_REGION} data-testid="watch-toasts">
      {toasts.map(toast => (
        <WatchToastCard key={toast.symbol} toast={toast} onOpenSymbol={onOpenSymbol} />
      ))}
    </div>
  );
}
