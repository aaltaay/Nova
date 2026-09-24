/**
 * Stop with friction: the button fires only after being held for the whole
 * interval. Letting go, leaving, or losing focus early cancels -- a recording
 * is locked, and a slip must not end it. Keyboard: hold Enter or Space.
 */
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { CAPTURE_STOP_HOLD_HINT, CAPTURE_STOP_HOLD_MS, CAPTURE_STOP_HOLD_STEP_MS } from './constants';
import './holdToStop.css';

interface Props {
  /** The accessible name; also the visible text unless `children` replaces it. */
  label: string;
  disabled?: boolean;
  /** Why `disabled` is set -- shown on hover and on a refused press (ux/whyTip.ts). */
  why?: string | null;
  holdMs?: number;
  onConfirm: () => void;
  testId?: string;
  /** Extra classes, for a host that lays the button out as one of its rows. */
  className?: string;
  /** Visible content in place of `label` (the symbol menu's icon, label and hint). */
  children?: ReactNode;
}

export function HoldToStopButton({
  label, disabled = false, why = null, holdMs = CAPTURE_STOP_HOLD_MS, onConfirm, testId, className, children,
}: Props) {
  const [progress, setProgress] = useState(0);
  const timer = useRef<number | null>(null);
  const ticker = useRef<number | null>(null);
  const startedAt = useRef(0);

  const cancel = () => {
    if (timer.current != null) { window.clearTimeout(timer.current); timer.current = null; }
    if (ticker.current != null) { window.clearInterval(ticker.current); ticker.current = null; }
    setProgress(0);
  };
  const begin = () => {
    if (disabled || timer.current != null) return;
    startedAt.current = Date.now();
    ticker.current = window.setInterval(() => {
      setProgress(Math.min(1, (Date.now() - startedAt.current) / holdMs));
    }, CAPTURE_STOP_HOLD_STEP_MS);
    timer.current = window.setTimeout(() => {
      cancel();
      onConfirm();
    }, holdMs);
  };
  useEffect(() => cancel, []);

  const isHoldKey = (event: KeyboardEvent<HTMLButtonElement>) => event.key === 'Enter' || event.key === ' ';
  // A locked Stop says why instead of the hold hint (ux/whyTip.ts).
  const lockWhy = disabled ? why || undefined : undefined;
  return (
    <button
      type="button"
      role="menuitem"
      className={`hold-to-stop${className ? ` ${className}` : ''}${progress > 0 ? ' hold-to-stop--holding' : ''}`}
      data-testid={testId}
      disabled={disabled}
      data-why={lockWhy}
      aria-label={label}
      title={lockWhy ? undefined : CAPTURE_STOP_HOLD_HINT}
      onPointerDown={(e) => { if (e.button === 0) begin(); }}
      onPointerUp={cancel}
      onPointerLeave={cancel}
      onPointerCancel={cancel}
      onKeyDown={(e) => { if (isHoldKey(e)) { e.preventDefault(); if (!e.repeat) begin(); } }}
      onKeyUp={(e) => { if (isHoldKey(e)) cancel(); }}
      onBlur={cancel}
      onClick={(e) => e.preventDefault()}
    >
      <span className="hold-to-stop__fill" style={{ width: `${(progress * 100).toFixed(1)}%` }} aria-hidden="true" />
      {children ?? <span className="hold-to-stop__label">{label}</span>}
    </button>
  );
}
