/**
 * The plan's level rows (ADR 036 amendment 2026-09-30, operator ask: "say our target is 1:2 ratio for
 * trades is too generic, sometimes we have to look at the very obvious resistance/support levels"; #845 took the
 * ratio out of the targets altogether): Room -- the first level of today's map over the entry, in cents, read against
 * the plan's targets: amber when it stands before target 1 (the target then needs it to break) -- the round number at
 * each target and at the stop (the stock's own scale: $5 and $10 on a $225 stock), the next round over the entry and
 * a round the price just broke or lost, and what the charts' trend lines say (2026-10-12: one in the way, the one
 * behind the stop, one that just broke). Trial T7 keeps its own reading of the Room (in R, under its registered
 * rule); it is said in the Room's hover only. Nothing here blocks or places.
 * Each row says it in a line; its hover gives what the level study measured, or how the line was drawn.
 */
import { tipProps } from '../ux';
import type { PlanLevelNote, PlanLineNote } from './levelTypes';
import type { StockPlan } from './types';

const ROWS = [
  ['room', 'Room'],
  ['target', 'Target 1'],
  ['target2', 'Target 2'],
  ['stop', 'Stop'],
  ['next', '$ next'],
  ['recent', '$ now'],
] as const;

type RowKey = (typeof ROWS)[number][0];

export function PlanLevels({ plan }: { plan: StockPlan }) {
  const lv = plan.levels;
  if (!lv) return null;
  return <LevelRowList levels={lv} lines={lv.lines} />;
}

/** A row's text without its own name: the held card's "Target 1 5.28 is 20c above" reads "5.28 is 20c above" under
 * its "Target 1" key. */
function shown(text: string, label: string): string {
  return text.startsWith(`${label} `) ? text.slice(label.length + 1) : text;
}

/** The rows themselves, for the plan's notes and for the trade you hold. */
export function LevelRowList({ levels: lv, lines = [] }: {
  levels: Partial<Record<RowKey, PlanLevelNote | null>>;
  /** The trend lines' rows, after the levels'. */
  lines?: PlanLineNote[];
}) {
  const rows: { key: string; label: string; note: PlanLevelNote }[] = [];
  for (const [key, label] of ROWS) {
    const note = lv[key];
    if (note) rows.push({ key, label, note });
  }
  for (const note of lines) rows.push({ key: `line-${note.role}`, label: 'Line', note });
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
          <span className="sr-levels__t">{shown(note.text, label)}</span>
        </li>
      ))}
    </ul>
  );
}
