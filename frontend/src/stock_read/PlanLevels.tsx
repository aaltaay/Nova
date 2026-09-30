/**
 * The plan's level rows (ADR 036 amendment 2026-09-30, operator ask: "say our target is 1:2 ratio for
 * trades is too generic, sometimes we have to look at the very obvious resistance/support levels"):
 * Room -- the first level of today's map over the entry, in R, amber under 2R while trial T7 runs -- the
 * half or whole dollar at the target and at the stop, the next round over the entry and a round the
 * price just broke or lost. The target stays 2R (the operator's call); nothing here blocks or places.
 * Each row says it in a line; its hover gives what the level study measured.
 */
import { tipProps } from '../ux';
import type { PlanLevelNote } from './levelTypes';
import type { StockPlan } from './types';

const ROWS = [
  ['room', 'Room'],
  ['target', 'Target'],
  ['stop', 'Stop'],
  ['next', '$ next'],
  ['recent', '$ now'],
] as const;

export function PlanLevels({ plan }: { plan: StockPlan }) {
  const lv = plan.levels;
  if (!lv) return null;
  const rows: { key: (typeof ROWS)[number][0]; label: string; note: PlanLevelNote }[] = [];
  for (const [key, label] of ROWS) {
    const note = lv[key];
    if (note) rows.push({ key, label, note });
  }
  if (rows.length === 0) return null;
  return (
    <ul className="sr-levels" data-testid="stock-read-levels" aria-label="The levels">
      {rows.map(({ key, label, note }) => (
        <li
          key={key}
          className={`sr-levels__row sr-levels__row--${note.state}`}
          data-testid={`stock-read-level-${key}`}
          {...tipProps(note.detail ?? note.text, label)}
        >
          <span className="sr-levels__k">{label}</span>
          <span className="sr-levels__t">{note.text}</span>
          {key === 'room' && lv.room.state === 'warn' && lv.room.trial && (
            <span className="sr-levels__pill" data-testid="stock-read-room-trial">in trial {lv.room.trial}</span>
          )}
        </li>
      ))}
    </ul>
  );
}
