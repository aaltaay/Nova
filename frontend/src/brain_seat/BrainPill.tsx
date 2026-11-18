/**
 * The brain's pill in the header (ADR 072 decisions 5, 10 and 11; approved mockup brain-switches v1 section 1): the
 * twin of Claude's. It always says what the brain is doing -- "Brain · Off", "Brain · Watching SSII", "Brain · In
 * XLAB +$42.00", "Brain · Done for today -$500", "Brain · Off · XLAB is yours to close" -- and, On with its program
 * not checking in, "Brain · On · its program is not running", so a brain that cannot trade never looks like one
 * that can. It carries the brain's On / Off switch: the switch flips at once, and a refused On (after its day stop,
 * after its flat-by time, on Live) is said under the pill in Nova's words. Clicking the words opens the panel (2).
 * It shows on every venue once the desk has read the traders view (on Live the switch is simply refused, in the
 * backend's words); never on the sample desk, which asks nothing.
 */
import { useEffect, useRef, useState } from 'react';
import { isSampleView } from '../sample_data/sampleNav';
import { useBrainSeat } from './brainSeatStore';
import { BRAIN_NOT_RUNNING_TIP, brainPillText, brainPillWords, type BrainPillWords } from './brainWords';
import { BrainMark } from './BrainMark';
import { BrainPanel } from './BrainPanel';
import { BrainSwitchButton, useBrainSwitch } from './BrainSwitch';
import './brainSeat.css';

/** The pill's words as the mockup sets them: the lead bold, the rest muted, the figure green or red in mono. */
function BrainPillText({ words }: { words: BrainPillWords }) {
  return (
    <span className="brain-pill__text">
      {words.lead}
      {words.rest ? <i> {words.rest}</i> : null}
      {words.pnl ? <> <span className={`brain-num is-${words.pnl.tone}`}>{words.pnl.text}</span></> : null}
      {words.tail ? <i> {words.tail}</i> : null}
    </span>
  );
}

export function BrainPill() {
  const { status, error } = useBrainSeat();
  const [open, setOpen] = useState(false);
  const press = useBrainSwitch();
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

  // Nothing before the first answer, as Claude's pill: the desk does not know the brain's state, and never says "Off"
  // for it. Once read, a read that fails keeps the last words and says why on the pill's tip and in the panel.
  if (isSampleView() || !status) return null;
  const words = brainPillWords(status);
  const notRunning = status.on && status.connected === false;
  // Paused: the tip says the whole reason (it trades Paper only, the desk is elsewhere, its trade keeps its exits).
  const tip = error ? `The brain: ${error}` : status.paused?.text || (notRunning ? BRAIN_NOT_RUNNING_TIP : undefined);
  return (
    <span className="brain-pill-wrap" ref={root}>
      <span className={`brain-pill brain-pill--${words.tone}`} data-testid="brain-pill" data-state={status.state}
        data-switch={status.on ? 'on' : 'off'}>
        <button
          type="button"
          className="brain-pill__open"
          data-testid="brain-pill-open"
          aria-expanded={open}
          aria-haspopup="dialog"
          aria-label={brainPillText(words)}
          title={tip ?? brainPillText(words)}
          onClick={() => setOpen(v => !v)}
        >
          <BrainMark />
          <BrainPillText words={words} />
        </button>
        <BrainSwitchButton status={status} press={press} />
      </span>
      {press.why && !open ? (
        <button type="button" className="brain-pill__why" role="alert" data-testid="brain-pill-why"
          onClick={press.clearWhy}>
          {press.why}
        </button>
      ) : null}
      {open ? <BrainPanel status={status} words={words} press={press} readError={error} /> : null}
    </span>
  );
}
