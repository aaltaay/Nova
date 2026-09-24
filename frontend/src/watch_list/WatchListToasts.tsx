/**
 * The watch list's toasts (operator asks, 2026-09-23 and 2026-09-24): "XYZ hit
 * HOD Momo", "XYZ is running up", and a watched symbol's setup climbing its
 * ladder -- "XYZ: bull flag armed". Mounted once with the app bar (the main
 * desk window, like the setup alert card, so two windows never announce the
 * same event twice). A toast leaves on its own after WATCH_TOAST_TTL_MS from
 * its newest event; hovering or focusing it holds it. Nothing here places or
 * stages an order.
 */
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { SETUP_KIND_LABELS, SETUP_TRIGGER_LEVEL_WORDS, TAPE_VERDICT_LABELS } from '../constants';
import { fmtStripClock, subscribeHodMomoLiveAlerts } from '../hod_momo';
import { setupLabel, setupShort, stateWords, useSetupsBoard, type SetupsBoard } from '../setups';
import { fmtPct, fmtPrice, fmtRvol, fmtVolume } from '../utils/quoteFormat';
import { tipProps } from '../ux/hoverTip';
import { setupClimbs, type SetupClimbMemory } from './setupClimbs';
import { WatchEyeIcon } from './WatchEyeIcon';
import {
  WATCH_SETUP_UNLISTED,
  WATCH_SETUP_UNLISTED_DETAIL,
  WATCH_TOAST_DISMISS,
  WATCH_TOAST_REGION,
  WATCH_TOAST_TTL_MS,
  WATCH_TOAST_UNWATCH,
  watchSetupLast,
  watchSetupTitle,
  watchToastCount,
  watchToastOpen,
  watchToastTitle,
} from './watchListConstants';
import { removeFromWatchList } from './watchListStore';
import {
  dismissWatchToast,
  getWatchToasts,
  noteWatchedHodAlert,
  noteWatchedSetupClimb,
  refreshWatchSetupLines,
  subscribeWatchToasts,
  type WatchSetupLine,
  type WatchToast,
} from './watchToasts';
import './watchList.css';

/**
 * Price · change · volume · RVOL of the newest alert; with no alert, the setup's
 * last price. An unknown fact is left out, never invented.
 */
export function watchToastFacts(toast: WatchToast): string {
  const { alert } = toast;
  if (!alert) {
    const last = toast.setups[0]?.row.last_price;
    return last != null && Number.isFinite(last) ? watchSetupLast(fmtPrice(last)) : '';
  }
  const facts: string[] = [];
  if (alert.price != null && Number.isFinite(alert.price)) facts.push(fmtPrice(alert.price));
  // Alerts carry percent points; fmtPct takes a fraction.
  if (alert.change_pct != null && Number.isFinite(alert.change_pct)) facts.push(fmtPct(alert.change_pct / 100));
  if (alert.volume != null && Number.isFinite(alert.volume)) facts.push(`Vol ${fmtVolume(alert.volume)}`);
  const rvol = fmtRvol(alert.rvol);
  if (rvol) facts.push(`RVOL ${rvol}`);
  return facts.join(' · ');
}

/** The title: the toast's newest event, a HOD Momo alert or a setup's climb. */
export function watchToastHeadline(toast: WatchToast): string {
  const { head, symbol } = toast;
  if (head.kind === 'hod') return watchToastTitle(symbol, toast.hod);
  const name = SETUP_KIND_LABELS[head.setupKind ?? ''] ?? setupLabel(head.setupType);
  return watchSetupTitle(symbol, name.toLowerCase(), head.stage, SETUP_TRIGGER_LEVEL_WORDS[head.setupType] ?? 'trigger');
}

/** HH:MM:SS ET of the newest event: the desk's one clock. */
function headClock(toast: WatchToast): string {
  if (toast.head.kind === 'setup') return fmtStripClock({ timestamp: '', created_ts: toast.head.at });
  return toast.alert ? fmtStripClock(toast.alert) : '';
}

/** A setup line's words after its chip: the scanner's own reason (the tape too when near), or why it is gone. */
export function watchSetupDetail(line: WatchSetupLine): string {
  if (!line.listed) return WATCH_SETUP_UNLISTED_DETAIL;
  const reason = (line.row.reason ?? '').replace(/ -- /g, ' — ');   // backend prose writes ASCII " -- "
  const verdict = line.row.state === 'near' ? line.row.tape?.verdict : undefined;
  return [reason, verdict ? TAPE_VERDICT_LABELS[verdict] ?? verdict : ''].filter(Boolean).join(' · ');
}

function SetupLine({ line }: { line: WatchSetupLine }) {
  const words = stateWords(line.row);
  const tip = line.listed ? words.tip : `${WATCH_SETUP_UNLISTED_DETAIL}\n\nLast listed as ${words.text}:\n${words.tip}`;
  return (
    <div
      className={`watch-toast__setup${line.listed ? '' : ' is-unlisted'}`}
      data-testid="watch-toast-setup"
      data-setup={line.setupType}
      {...tipProps(tip, words.title)}
    >
      <span className="watch-toast__setup-name">{setupShort(line.setupType)}</span>
      <span className={`pillar-chip setups-state setups-state--${line.listed ? line.row.state : 'watching'}`}>
        {line.listed ? words.text : WATCH_SETUP_UNLISTED}
      </span>
      <span className="watch-toast__setup-detail">{watchSetupDetail(line)}</span>
    </div>
  );
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
  const hodLine = strategies || toast.count > 1 ? (
    <span className="watch-toast__body" data-testid="watch-toast-body">
      {strategies}
      {toast.count > 1 ? <span className="watch-toast__count"> · {watchToastCount(toast.count)}</span> : null}
    </span>
  ) : null;
  const setupLines = toast.setups.map(line => <SetupLine key={line.setupType} line={line} />);
  // The line the title speaks of sits right under it.
  const setupFirst = toast.head.kind === 'setup';
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
          <strong className="watch-toast__title" data-testid="watch-toast-title">{watchToastHeadline(toast)}</strong>
          <span className="watch-toast__time">{headClock(toast)}</span>
        </div>
        {setupFirst ? setupLines : hodLine}
        {setupFirst ? hodLine : setupLines}
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

/**
 * The setup scanner's live frames into the toasts: a watched symbol's climb, and
 * the setup lines on screen. A dropped socket or the Sim eyes' board forgets the
 * ladder; the next live frame is then read silently, so nothing old is announced.
 */
function useWatchedSetupClimbs(): void {
  const stream = useSetupsBoard();
  const board = stream?.board ?? null;
  const connected = stream?.connected ?? false;
  const memory = useRef<SetupClimbMemory | null>(null);
  // The frame on hand when the ladder was forgotten: a reconnect waits for a fresh one.
  const stale = useRef<SetupsBoard | null>(null);
  useEffect(() => {
    if (!board || !connected || board.source === 'sim') {
      memory.current = null;
      stale.current = board;
      return;
    }
    if (board === stale.current) return;
    stale.current = null;
    const read = setupClimbs(memory.current, board, Date.now());
    memory.current = read.memory;
    for (const climb of read.climbs) noteWatchedSetupClimb(climb);
    refreshWatchSetupLines(board.rows ?? []);
  }, [board, connected]);
}

export function WatchListToasts({ onOpenSymbol }: { onOpenSymbol?: (symbol: string) => void }) {
  const toasts = useSyncExternalStore(subscribeWatchToasts, getWatchToasts, getWatchToasts);
  useEffect(() => subscribeHodMomoLiveAlerts(alert => {
    noteWatchedHodAlert(alert);
  }), []);
  useWatchedSetupClimbs();

  if (toasts.length === 0) return null;
  return (
    <div className="watch-toasts" role="region" aria-label={WATCH_TOAST_REGION} data-testid="watch-toasts">
      {toasts.map(toast => (
        <WatchToastCard key={toast.symbol} toast={toast} onOpenSymbol={onOpenSymbol} />
      ))}
    </div>
  );
}
