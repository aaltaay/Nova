/** Advise ticker gate -- matches backend advise.service._SYMBOL_RE. */

export const ADVISE_SYMBOL_RE = /^[A-Z][A-Z0-9.-]{0,11}$/;

export function normalizeAdviseSymbol(value: string): string {
  return value.trim().toUpperCase();
}

export function isAdviseSymbol(value: string): boolean {
  return ADVISE_SYMBOL_RE.test(normalizeAdviseSymbol(value));
}
