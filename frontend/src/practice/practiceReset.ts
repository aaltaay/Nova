/** Pure helpers for the Reset practice account form (ADR 020). */
import {
  PRACTICE_STARTING_CASH_MAX,
  PRACTICE_STARTING_CASH_MIN,
  practiceStartingCashInvalid,
} from '../constantGroups/practice';
import { formatMoney } from '../utils/formatMoney';

export type StartingCashParse =
  | { ok: true; value: number | null }
  | { ok: false; error: string };

/** Blank keeps the current starting cash; otherwise a whole-dollar amount inside the bounds. */
export function parseStartingCash(raw: string): StartingCashParse {
  const text = raw.replace(/[$,\s]/g, '');
  if (!text) return { ok: true, value: null };
  const value = Number(text);
  const invalid = () => ({
    ok: false as const,
    error: practiceStartingCashInvalid(
      formatMoney(PRACTICE_STARTING_CASH_MIN, 0),
      formatMoney(PRACTICE_STARTING_CASH_MAX, 0),
    ),
  });
  if (!/^\d+$/.test(text) || !Number.isFinite(value)) return invalid();
  if (value < PRACTICE_STARTING_CASH_MIN || value > PRACTICE_STARTING_CASH_MAX) return invalid();
  return { ok: true, value };
}
