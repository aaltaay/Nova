/**
 * Stop with friction: the button fires only after being held for the whole
 * interval. Letting go, leaving, or losing focus early cancels -- a recording
 * is locked, and a slip must not end it. Keyboard: hold Enter or Space.
 */
import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { CAPTURE_STOP_HOLD_HINT, CAPTURE_STOP_HOLD_MS, CAPTURE_STOP_HOLD_STEP_MS } from './constants';
import './holdToStop.css';

interface Props {
  label: string;
  disabled?: boolean;
  holdMs?: number;
  onConfirm: () => void;
  testId?: string;
}

export function HoldToStopButton({ label, disabled = false, holdMs = CAPTURE_STOP_HOLD_MS, onConfirm, testId }: Props) {
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
  return (
    <button
      type="button"
      role="menuitem"
      className={`hold-to-stop${progress > 0 ? ' hold-to-stop--holding' : ''}`}
      data-testid={testId}
      disabled={disabled}
      aria-label={label}
      title={CAPTURE_STOP_HOLD_HINT}
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
      <span className="hold-to-stop__label">{label}</span>
    </button>
  );
}
