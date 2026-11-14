/**
 * A template's numbers in words (ADR 029): the editor's values, shown and typed, for the parameters the scanner
 * runs on (Settings > Strategies, ADR 072). Pure.
 */
import { money, num, trim, type Values } from './templateParts';
import type { ParamSpec, ParamValue } from './templateTypes';

export { money };

/** One value as the operator reads it: "$0.20", "5%", "10 bars", "07:00 ET", "off". */
export function formatValue(spec: ParamSpec, value: ParamValue | undefined): string {
  if (value === null || value === undefined) return spec.nullable ? 'off' : '—';
  if (spec.kind === 'bool') return value ? 'on' : 'off';
  if (spec.kind === 'time') return `${value} ET`;
  if (spec.kind === 'choice') return spec.choices.find(c => c.value === value)?.label ?? String(value);
  const n = num(value);
  if (n == null) return String(value);
  // "$ past the entry" (the target menu's fixed amount, #845) reads "$0.20 past the entry".
  if (spec.unit.startsWith('$')) return `${money(n)}${spec.unit.slice(1)}`;
  if (spec.unit.startsWith('%')) return `${trim(n, 2)}${spec.unit}`;
  if (spec.unit === 'x' || spec.unit === 'R') return `${trim(n, 2)}${spec.unit}`;
  if (spec.unit.startsWith('M shares')) return `${trim(n, 1)}M`;
  if (spec.unit === 'shares') return `${Math.round(n).toLocaleString('en-US')} shares`;
  return spec.unit ? `${trim(n, 3)} ${spec.unit}` : trim(n, 3);
}

/** The typed text of an input -> a value, or the reason it is refused (the backend checks again). */
export function parseInput(spec: ParamSpec, raw: string): { value: ParamValue } | { error: string } {
  const text = raw.trim();
  if (text === '' && spec.nullable) return { value: null };
  if (spec.kind === 'time') {
    return /^([01]\d|2[0-3]):[0-5]\d$/.test(text) ? { value: text } : { error: 'a time like 07:00' };
  }
  const n = Number(text);
  if (text === '' || !Number.isFinite(n)) return { error: 'a number' };
  if (spec.kind === 'int' && !Number.isInteger(n)) return { error: 'a whole number' };
  if (typeof spec.min === 'number' && n < spec.min) return { error: `at least ${spec.min}` };
  if (typeof spec.max === 'number' && n > spec.max) return { error: `at most ${spec.max}` };
  return { value: n };
}

export function changedKeys(a: Values, b: Values): string[] {
  return Object.keys({ ...a, ...b }).filter(k => a[k] !== b[k]);
}
