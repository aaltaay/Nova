/**
 * A strategy's bot rules on its card (ADR 044): the grades Nova buys (A and B, or A only; C never), setups a
 * stock a day (the 1st, or the 1st and 2nd), and the bot window. They are the template in play's bot-group
 * parameters: changing one never starts the read-out over, and the built-in template takes them too.
 */
import { useState } from 'react';
import { tipProps, whyProps } from '../ux';
import { updateTemplate } from './templatesApi';
import type { ParamValue, SetupTemplates } from './templateTypes';

const GRADES: [string, string][] = [['A', 'A only'], ['AB', 'A and B']];
const PER_DAY: [number, string][] = [[1, '1st'], [2, '1st and 2nd']];
const TIMES = Array.from({ length: (16 - 4) * 4 + 1 }, (_, i) => {
  const m = 4 * 60 + i * 15;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
});

export function BotStrategyRules({ setup, templates, onApply }: {
  setup: string;
  templates: SetupTemplates | null;
  onApply: (next: SetupTemplates) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inPlay = templates?.templates.find(t => t.id === templates.in_play) ?? null;
  const values = inPlay?.values ?? {};
  const has = (key: string) => key in values;
  const grades = typeof values.bot_grades === 'string' ? values.bot_grades : 'AB';
  const perDay = typeof values.bot_setups_a_day === 'number' ? values.bot_setups_a_day : 1;
  const start = typeof values.bot_window_start === 'string' ? values.bot_window_start : null;
  const end = typeof values.bot_window_end === 'string' ? values.bot_window_end : null;
  const lock = busy ? 'Saving the template…' : !inPlay ? 'The template in play is still loading.'
    : !has('bot_grades') ? 'This backend is older than the strategy rows: reload the backend after the update.' : null;
  const save = async (patch: Record<string, ParamValue>) => {
    if (!inPlay) return;
    setBusy(true);
    try {
      onApply(await updateTemplate(setup, inPlay.id, { values: patch }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  const seg = <T extends string | number>(label: string, options: [T, string][], value: T, key: string, tip: string) => (
    <span className="bots-rules__item" {...tipProps(tip, label)}>
      <span className="bots-rules__label">{label}</span>
      <span className="bots-mini-seg" role="radiogroup" aria-label={label}>
        {options.map(([v, text]) => (
          <button key={String(v)} type="button" role="radio" aria-checked={value === v} disabled={lock !== null}
            {...(lock ? whyProps(true, lock) : {})} onClick={() => { if (value !== v) void save({ [key]: v }); }}
            data-testid={`bots-rules-${setup}-${key}-${v}`}>{text}</button>
        ))}
      </span>
    </span>
  );
  return (
    <div className="bots-rules" data-testid={`bots-rules-${setup}`}>
      {seg('Grades', GRADES, grades, 'bot_grades', 'Which grades Nova may buy at On. C is never a trade.')}
      <span className="bots-muted bots-rules__never">C never</span>
      {seg('Setups a stock a day', PER_DAY, perDay, 'bot_setups_a_day',
        'How many setups of this strategy Nova may buy on one stock in a day: the 1st only, or the 1st and the 2nd.')}
      <span className="bots-rules__item" {...tipProps('Nova sends an entry only inside this window (the venue\'s clock). It sits inside the arming window.', 'Bot window')}>
        <span className="bots-rules__label">Bot window</span>
        <select aria-label="Bot window start" value={start ?? ''} disabled={lock !== null || !start} {...(lock ? whyProps(true, lock) : {})}
          onChange={e => void save({ bot_window_start: e.target.value })} data-testid={`bots-rules-${setup}-start`}>
          {start && !TIMES.includes(start) ? <option value={start}>{start}</option> : null}
          {TIMES.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <span>–</span>
        <select aria-label="Bot window end" value={end ?? ''} disabled={lock !== null || !end} {...(lock ? whyProps(true, lock) : {})}
          onChange={e => void save({ bot_window_end: e.target.value })} data-testid={`bots-rules-${setup}-end`}>
          {end && !TIMES.includes(end) ? <option value={end}>{end}</option> : null}
          {TIMES.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </span>
      {error ? <span className="bots-rules__error" role="alert">{error}</span> : null}
    </div>
  );
}
