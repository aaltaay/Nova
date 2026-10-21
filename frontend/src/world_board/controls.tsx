/**
 * The world boards' controls (the Global and Forex pages, ADR 060, 061): the segmented switch, the notes on one line
 * in the head (the pages never scroll, so a note never pushes the board down), and "How to read" -- the page's
 * definitions over its list on hover or focus, kept open by a click. `prefix` names each page's test ids.
 */
import { useState, type ReactNode } from 'react';

export interface Note {
  id: string;
  text: string;
  warn?: boolean;
}

export function Seg<T extends string>({ value, options, labels, onPick, testId }: {
  value: T; options: readonly T[]; labels: Record<T, string>; onPick: (v: T) => void; testId: string;
}) {
  return (
    <div className="gb-seg" role="group" data-testid={testId}>
      {options.map((o) => (
        <button key={o} type="button" className={o === value ? 'is-on' : ''} aria-pressed={o === value}
          data-testid={`${testId}-${o}`} onClick={() => onPick(o)}>{labels[o]}</button>
      ))}
    </div>
  );
}

/** Every note on one line; the full words on hover. */
export function StatusLine({ notes, prefix }: { notes: Note[]; prefix: string }) {
  if (!notes.length) return <span className="gb-status" />;
  return (
    <span className="gb-status" role="status" title={notes.map((n) => n.text).join('\n')} data-testid={`${prefix}-status`}>
      {notes.map((n) => (
        <span key={n.id} className={n.warn ? 'is-warn' : undefined}
          data-testid={n.id === 'period' ? `${prefix}-period-loading` : `${prefix}-note-${n.id}`}>{n.text}</span>
      ))}
    </span>
  );
}

export function HowToRead({ label, prefix, children }: { label: string; prefix: string; children: ReactNode }) {
  const [pinned, setPinned] = useState(false);
  const [hover, setHover] = useState(false);
  const open = pinned || hover;
  return (
    <span className="gb-howto" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <button type="button" className={`gb-howto__btn${pinned ? ' is-on' : ''}`} aria-expanded={open}
        data-testid={`${prefix}-how-to-read`} onClick={() => setPinned((p) => !p)}
        onFocus={() => setHover(true)} onBlur={() => setHover(false)}>
        {label}
      </button>
      {open ? <div className="gb-defs" role="note" data-testid={`${prefix}-defs`}>{children}</div> : null}
    </span>
  );
}
