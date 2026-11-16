/**
 * A template's numbers in the operator's words (ADR 029): the pieces the template editor formats its values with
 * (`templateFormat.ts`). Pure.
 */
import type { ParamValue } from './templateTypes';

export type Values = Record<string, ParamValue>;

export function num(v: ParamValue | undefined): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

export function trim(n: number, digits = 2): string {
  return n.toFixed(digits).replace(/\.?0+$/, '');
}

export function money(n: number): string {
  const digits = Math.abs(n) < 1 && Math.round(n * 1000) % 10 !== 0 ? 3 : 2;
  return `$${n.toFixed(digits)}`;
}
