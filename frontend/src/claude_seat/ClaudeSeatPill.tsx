/**
 * The Claude pill in the header (ADR 068, the approved design's 1): always says what Claude is doing -- "Claude ·
 * Buy set SMPL 4.39", "Claude · In SMPL +$42.00", "Waiting for a Level 2 line", "Paused by you", "Done for today". A
 * click opens the panel (2). It shows while the seat is on, and "Off" muted on a day it was on; never on the
 * sample desk. It also hosts Claude's toasts (5), so the header mounts one element.
 */
import { useEffect, useRef, useState } from 'react';
import { isSampleView } from '../sample_data/sampleNav';
import { useClaudeSeat } from './claudeSeatStore';
import { pillShown, pillTone } from './claudeSeatWords';
import { ClaudeMark } from './ClaudeMark';
import { ClaudeSeatPanel } from './ClaudeSeatPanel';
import { ClaudeSeatToasts } from './ClaudeSeatToasts';
import './claudeSeat.css';

export function ClaudeSeatPill() {
  const { status, error } = useClaudeSeat();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    const away = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', away);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);

  if (isSampleView()) return null;
  // One toast host for the window's life (first child, both ways): it must not remount when the pill appears.
  const pill = status && pillShown(status) ? status : null;
  const tone = pill ? pillTone(pill) : 'off';
  return (
    <>
      <ClaudeSeatToasts />
      {pill ? (
        <span className="claude-pill-wrap" ref={root}>
          <button
            type="button"
            className={`claude-pill claude-pill--${tone}`}
            data-testid="claude-pill"
            data-state={pill.state}
            aria-expanded={open}
            aria-haspopup="dialog"
            title={error ? `Claude's seat: ${error}` : undefined}
            onClick={() => setOpen(v => !v)}
          >
            <ClaudeMark tone={tone} />
            <span className="claude-pill__text">{pill.text}</span>
            <span className="claude-pill__caret" aria-hidden="true">▾</span>
          </button>
          {open ? <ClaudeSeatPanel status={pill} /> : null}
        </span>
      ) : null}
    </>
  );
}
