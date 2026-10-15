/**
 * A host bot's money rules, edited in place (ADR 055): the step, the adds it follows, its allowance, longs only or
 * both sides with the short's buy stop, and positions already open. Each change is sent as it is made; the backend
 * checks it against its bounds and says why when it refuses (never clamped in silence).
 */
import { useEffect, useState } from 'react';
import { LT_ADDS_CHOICES, LT_SIDES_WORDS, LT_TAKE_OPEN_WORDS, ltAddsWords } from '../constantGroups/live_trader';
import type { LtPatch, LtSettings } from './liveTraderTypes';

interface Props {
  name: string;
  settings: LtSettings;
  busy: boolean;
  onPatch: (name: string, body: LtPatch) => Promise<void>;
}

function Money({ label, value, field, name, busy, onPatch, suffix = '' }: {
  label: string; value: number; field: 'step_usd' | 'allowance_usd' | 'short_stop_pct'; name: string; busy: boolean;
  onPatch: Props['onPatch']; suffix?: string;
}) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);
  const commit = () => {
    const n = Number(draft);
    if (draft.trim() === '' || !Number.isFinite(n)) {
      setDraft(String(value));
      return;
    }
    if (n !== value) void onPatch(name, { [field]: n });
  };
  return (
    <label className="lt-edit__item">
      <span className="lt-label">{label}</span>
      <input type="number" inputMode="decimal" value={draft} disabled={busy} data-testid={`lt-edit-${field}-${name}`}
        onChange={e => setDraft(e.target.value)} onBlur={commit}
        onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />
      {suffix ? <span className="lt-muted">{suffix}</span> : null}
    </label>
  );
}

function Seg<T>({ label, value, options, words, onPick, busy, testId }: {
  label: string; value: T; options: readonly T[]; words: (v: T) => string; onPick: (v: T) => void; busy: boolean;
  testId: string;
}) {
  return (
    <span className="lt-edit__item">
      <span className="lt-label">{label}</span>
      <span className="bots-mini-seg" role="radiogroup" aria-label={label}>
        {options.map(opt => (
          <button key={String(opt)} type="button" role="radio" aria-checked={value === opt} disabled={busy}
            data-testid={`${testId}-${String(opt)}`} onClick={() => { if (value !== opt) onPick(opt); }}>
            {words(opt)}
          </button>
        ))}
      </span>
    </span>
  );
}

export function LiveTraderSettings({ name, settings: st, busy, onPatch }: Props) {
  return (
    <div className="lt-edit" data-testid={`lt-edit-${name}`}>
      <Money label="Step" value={st.step_usd} field="step_usd" name={name} busy={busy} onPatch={onPatch}
        suffix="$ a step; 1 share when a share costs more" />
      <Seg label="Adds" value={st.adds} options={LT_ADDS_CHOICES} words={ltAddsWords} busy={busy}
        testId={`lt-edit-adds-${name}`} onPick={v => void onPatch(name, { adds: v })} />
      <Money label="Allowance" value={st.allowance_usd} field="allowance_usd" name={name} busy={busy}
        onPatch={onPatch} suffix="$ in the market at once" />
      <Seg label="Sides" value={st.sides} options={['long', 'both'] as const} words={v => LT_SIDES_WORDS[v]} busy={busy}
        testId={`lt-edit-sides-${name}`} onPick={v => void onPatch(name, { sides: v })} />
      {st.sides === 'both' ? (
        <Money label="Short stop" value={st.short_stop_pct} field="short_stop_pct" name={name} busy={busy}
          onPatch={onPatch} suffix="% over the entry" />
      ) : null}
      <Seg label="Already open" value={st.take_open} options={[true, false] as const}
        words={v => (v ? LT_TAKE_OPEN_WORDS.take : LT_TAKE_OPEN_WORDS.skip)} busy={busy}
        testId={`lt-edit-open-${name}`} onPick={v => void onPatch(name, { take_open: v })} />
    </div>
  );
}
