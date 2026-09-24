/**
 * One parameter of a setup template (ADR 029): its label and what it does, the
 * value in its own unit, and the default when it differs. A locked field (the
 * pre-registered default, or a template being saved) says why on hover.
 */
import { useEffect, useId, useState } from 'react';
import { BOTS_PARAM_FILTER_OFF_WHY } from '../constantGroups/bots_page';
import { formatValue, parseInput } from './templateFormat';
import type { ParamSpec, ParamValue } from './templateTypes';

interface Props {
  spec: ParamSpec;
  value: ParamValue;
  /** Why the field cannot be edited, or null when it can. */
  lockedWhy: string | null;
  /** The backend's refusal for this field, when the last save named it. */
  serverError?: string | null;
  onChange: (key: string, value: ParamValue, error: string | null) => void;
}

function textOf(value: ParamValue): string {
  return value === null || value === undefined ? '' : String(value);
}

export function BotParamField({ spec, value, lockedWhy, serverError = null, onChange }: Props) {
  const id = useId();
  const [raw, setRaw] = useState(textOf(value));
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setRaw(textOf(value));
    setError(null);
  }, [value]);

  const locked = lockedWhy != null;
  const changed = value !== spec.default;
  const shownError = error ?? serverError;

  function commitText(text: string) {
    setRaw(text);
    const parsed = parseInput(spec, text);
    if ('error' in parsed) {
      setError(`${spec.label} is ${parsed.error}`);
      onChange(spec.key, value, `${spec.label} is ${parsed.error}`);
      return;
    }
    setError(null);
    onChange(spec.key, parsed.value, null);
  }

  let control;
  if (spec.kind === 'bool') {
    control = (
      <input id={id} type="checkbox" role="switch" checked={Boolean(value)} aria-checked={Boolean(value)}
        data-testid={`bots-param-${spec.key}`} disabled={locked} data-why={lockedWhy ?? undefined}
        onChange={e => onChange(spec.key, e.target.checked, null)} />
    );
  } else if (spec.kind === 'choice') {
    control = (
      <select id={id} value={String(value ?? '')} data-testid={`bots-param-${spec.key}`} disabled={locked}
        data-why={lockedWhy ?? undefined} onChange={e => onChange(spec.key, e.target.value, null)}>
        {spec.choices.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
      </select>
    );
  } else {
    const off = spec.nullable && value === null;
    control = (
      <span className="bots-param__num">
        {spec.nullable ? (
          <input type="checkbox" aria-label={`Use ${spec.label}`} checked={!off} data-testid={`bots-param-${spec.key}-on`}
            disabled={locked} data-why={lockedWhy ?? undefined}
            onChange={e => {
              if (e.target.checked) commitText(textOf(spec.min ?? 0));
              else onChange(spec.key, null, null);
            }} />
        ) : null}
        <input id={id} type="text" inputMode={spec.kind === 'time' ? 'text' : 'decimal'} value={off ? '' : raw}
          placeholder={off ? 'off' : undefined} data-testid={`bots-param-${spec.key}`}
          aria-invalid={shownError ? true : undefined} disabled={locked || off}
          data-why={lockedWhy ?? (off ? BOTS_PARAM_FILTER_OFF_WHY : undefined)}
          onChange={e => commitText(e.target.value)} />
        {spec.unit ? <span className="bots-param__unit">{spec.unit}</span> : null}
      </span>
    );
  }

  return (
    <div className={`bots-param${changed ? ' is-changed' : ''}${shownError ? ' is-error' : ''}`}
      data-testid={`bots-param-row-${spec.key}`}>
      <label htmlFor={id} className="bots-param__label">
        {spec.label}
        {spec.help ? <small>{spec.help}</small> : null}
      </label>
      <div className="bots-param__control">{control}</div>
      <span className="bots-param__meta">
        {changed ? `default ${formatValue(spec, spec.default)}` : 'default'}
        {spec.live ? '' : ' · no scanner yet'}
      </span>
      {shownError ? <span className="bots-param__error" role="alert">{shownError}</span> : null}
    </div>
  );
}
