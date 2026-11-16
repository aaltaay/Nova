/**
 * The Claude pill in the header (ADR 068, the approved design's 1; ADR 072, mockup brain-switches v1 section 1):
 * always says what Claude is doing -- "Claude · Buy set SMPL 4.39", "Claude · In SMPL +$42.00", "Waiting for a
 * Level 2 line", "Done for today" -- and carries Claude's On / Off switch. Clicking the words opens the panel (2);
 * the switch flips at once, and a refused On is said under the pill in Nova's words. It always shows -- "Claude ·
 * Off" muted while the seat or the switch is off, so the operator sees Claude is off -- never on the sample desk. It
 * also hosts Claude's toasts (5), so the header mounts one element.
 */
import { useEffect, useRef, useState } from 'react';
import { isSampleView } from '../sample_data/sampleNav';
import { useClaudeSeat } from './claudeSeatStore';
import { pillShown, pillTone } from './claudeSeatWords';
import { ClaudeMark } from './ClaudeMark';
import { ClaudeSeatPanel } from './ClaudeSeatPanel';
import { ClaudeSeatToasts } from './ClaudeSeatToasts';
import { ClaudeSwitchButton, useClaudeSwitch } from './ClaudeSwitch';
import './claudeSeat.css';

export function ClaudeSeatPill() {
  const { status, error } = useClaudeSeat();
  const [open, setOpen] = useState(false);
  const press = useClaudeSwitch();
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
          <span className={`claude-pill claude-pill--${tone}`} data-testid="claude-pill" data-state={pill.state}
            data-switch={pill.switch ? (pill.switch.on ? 'on' : 'off') : undefined}>
            <button
              type="button"
              className="claude-pill__open"
              data-testid="claude-pill-open"
              aria-expanded={open}
              aria-haspopup="dialog"
              title={error ? `Claude's seat: ${error}` : undefined}
              onClick={() => setOpen(v => !v)}
            >
              <ClaudeMark tone={tone} />
              <span className="claude-pill__text">{pill.text}</span>
            </button>
            {pill.switch ? <ClaudeSwitchButton sw={pill.switch} press={press} /> : null}
          </span>
          {press.why && !open ? (
            <button type="button" className="claude-pill__why" role="alert" data-testid="claude-pill-why"
              onClick={press.clearWhy}>
              {press.why}
            </button>
          ) : null}
          {open ? <ClaudeSeatPanel status={pill} press={press} /> : null}
        </span>
      ) : null}
    </>
  );
}
