/**
 * One sleeve cap as a slider (approved mockup v4). The value follows the thumb
 * at once, and the session is PATCHed once the operator lets go -- on release,
 * or a short pause after the last keyboard step -- never once per pixel, and
 * never with a half-typed number the backend would refuse.
 */
import { useEffect, useRef, useState } from 'react';
import { BOTS_SLIDER_COMMIT_MS } from '../constantGroups/bots_page';

interface Props {
  label: string;
  testId: string;
  value: number;
  min: number;
  max: number;
  step: number;
  /** How the value reads beside the label ("1", "$50.00", "3 s"). */
  format: (v: number) => string;
  minLabel: string;
  maxLabel: string;
  disabled?: boolean;
  onCommit: (v: number) => void;
}

export function BotSleeveSlider({ label, testId, value, min, max, step, format, minLabel, maxLabel, disabled, onCommit }: Props) {
  const [draft, setDraft] = useState(value);
  const pending = useRef<number | null>(null);
  const timer = useRef<number | null>(null);

  // A new session value (another window, the backend's clamp) wins unless a change is in flight.
  useEffect(() => {
    if (pending.current == null) setDraft(value);
  }, [value]);

  useEffect(() => () => {
    if (timer.current != null) window.clearTimeout(timer.current);
  }, []);

  function flush() {
    if (timer.current != null) window.clearTimeout(timer.current);
    timer.current = null;
    const next = pending.current;
    pending.current = null;
    if (next != null && next !== value) onCommit(next);
  }

  function change(raw: string) {
    const next = Number(raw);
    if (!Number.isFinite(next)) return;
    setDraft(next);
    pending.current = next;
    if (timer.current != null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, BOTS_SLIDER_COMMIT_MS);
  }

  const pct = max > min ? ((draft - min) / (max - min)) * 100 : 0;
  return (
    <label className="bots-slider">
      <span className="bots-slider__head"><span>{label}</span><b>{format(draft)}</b></span>
      <input
        type="range"
        data-testid={testId}
        min={min}
        max={max}
        step={step}
        value={draft}
        disabled={disabled}
        style={{ ['--bots-fill' as string]: `${pct}%` }}
        onChange={e => change(e.target.value)}
        onPointerUp={flush}
        onKeyUp={flush}
        onBlur={flush}
      />
      <span className="bots-slider__scale"><small>{minLabel}</small><small>{maxLabel}</small></span>
    </label>
  );
}
