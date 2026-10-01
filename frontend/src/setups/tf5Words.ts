/**
 * What the 5-minute chart says about a 1-minute setup (operator ask 2026-09-30: "sometimes the 1-minute
 * setup aligns well with the 5-minute setup"; trial T8). The scanner reads it from its own minutes when the
 * pattern's leg makes its high, when the setup arms and at the trigger (`row.tf5_at` says which): the last
 * complete 5-minute candle's close against the 9 EMA of 5-minute closes, and the 5-minute MACD histogram.
 * It is shown only: nothing blocks on it, and a trial on new days decides whether "against" ever warns.
 * Pure: a row in, a chip's words out.
 */
import { etHm, type Words } from './setupWords';
import type { SetupRow } from './types';

export type Tf5Tone = 'agrees' | 'against';

const WHEN: Record<string, string> = {
  trigger: 'at the trigger',
  armed: 'when it armed',
  forming: 'when its leg made its high',
};

export const TF5_TRIAL_NOTE =
  'In trial T8: shown only, it never blocks a trade. A trial on new days decides whether "against" ever becomes ' +
  'a warning (on five years of history it leaned the right way and did not hold).';

/** The chip: "5m ✓" agrees, "5m ✗" against; null while the scanner has no complete 5-minute candle. */
export function tf5Words(row: SetupRow): (Words & { tone: Tf5Tone }) | null {
  const r = row.tf5;
  if (!r || typeof r.agrees !== 'boolean') return null;
  const when = WHEN[row.tf5_at ?? ''] ?? 'last';
  const ema = `closed ${r.above_ema9 ? 'over' : 'under'} its 9 EMA (${r.ema9.toFixed(2)})`;
  const macd = `its MACD is ${r.macd_up ? 'up' : 'down'}`;
  const verdict = r.agrees
    ? 'The 5-minute chart agrees with this 1-minute setup.'
    : 'The 5-minute chart does not agree: it needs both its close over the 9 EMA and its MACD up.';
  return {
    text: r.agrees ? '5m ✓' : '5m ✗',
    title: r.agrees ? '5-minute agrees' : '5-minute against',
    tone: r.agrees ? 'agrees' : 'against',
    tip: `${verdict}\nRead ${when}, on the ${etHm(r.as_of)} 5-minute candle: it ${ema}, and ${macd}.\n${TF5_TRIAL_NOTE}`,
  };
}
