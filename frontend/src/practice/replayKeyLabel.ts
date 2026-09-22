/**
 * The Sim scratch account's `replay_key` names the replay it is bound to. The
 * backend sends the ledger's key as it stores it -- a list
 * `[source, symbol, date, start?, end?]` (`practice/ledger.py` `snapshot`) --
 * or a plain string in older payloads. Render it as one readable label; never
 * call string methods on it blind (2026-09-22: `replay_key?.trim is not a
 * function` took the whole Trader view down after a historical download).
 */
import { PRACTICE_REPLAY_SOURCE_LABELS } from '../constantGroups/practice';

export type ReplayKeyWire = string | ReadonlyArray<string | number | null> | null | undefined;

export function formatReplayKey(key: ReplayKeyWire): string {
  if (key == null) return '';
  if (typeof key === 'string') return key.trim();
  if (!Array.isArray(key)) return String(key).trim();
  const parts = key.map((p) => (p == null ? '' : String(p).trim())).filter(Boolean);
  if (parts.length === 0) return '';
  const [source, symbol, date, start, end] = parts;
  const head = [symbol, date].filter(Boolean).join(' · ');
  const window = start && end ? ` · ${start}–${end}` : start ? ` · ${start}` : '';
  const kind = source ? PRACTICE_REPLAY_SOURCE_LABELS[source] ?? source : '';
  const label = `${head}${window}`;
  if (!label) return kind;
  return kind ? `${label} (${kind})` : label;
}
