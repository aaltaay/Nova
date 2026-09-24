/** The sheet's Signals tab: every row of the read, by group, with a one-line summary of the tiles and
 * the plan, filters by what a row says (for it, against it, caution, unknown) and a search. */
import { useEffect, useMemo, useRef, useState } from 'react';
import { hhmmEt } from './timeWords';
import { STATE_WORDS, TILE_NAMES } from './constants';
import { fmtPx, rrText, setupName } from './planMath';
import { GroupHead, ReadRowList } from './ReadRows';
import type { ReadGroupId, ReadRow, ReadState, StockRead } from './types';

type Filter = 'all' | ReadState;
const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'ok', label: STATE_WORDS.ok },
  { id: 'bad', label: STATE_WORDS.bad },
  { id: 'warn', label: STATE_WORDS.warn },
  { id: 'unknown', label: STATE_WORDS.unknown },
  { id: 'info', label: 'Facts' },
];

/** "APUS at 15:03 ET: In play Yes · Setups Flag forming · ... The plan: ...". */
export function readSummary(read: StockRead): string {
  const tiles = read.groups.map(g => `${TILE_NAMES[g.id] ?? g.label} ${g.value || '—'}`).join(' · ');
  const p = read.plan;
  let plan = 'No plan: nothing is forming.';
  if (p) {
    const what = p.source === 'manual' ? 'your plan' : `${setupName(p.setup_type).toLowerCase()} ${p.state}`;
    plan = `The plan (${what}): entry ${fmtPx(p.entry)}, stop ${fmtPx(p.stop)}, target ${fmtPx(p.target)}, `
      + `${rrText(p.rr)}.`;
  }
  return `${read.symbol} at ${hhmmEt(read.generated_at)} ET: ${tiles}. ${plan}`;
}

function matches(row: ReadRow, q: string): boolean {
  if (!q) return true;
  const hay = `${row.label} ${row.value} ${row.detail ?? ''} ${row.source}`.toLowerCase();
  return q.split(/\s+/).every(w => hay.includes(w));
}

export function SignalsTab({ read, focusGroup }: { read: StockRead; focusGroup: ReadGroupId | null }) {
  const [filter, setFilter] = useState<Filter>('all');
  const [query, setQuery] = useState('');
  const bodyRef = useRef<HTMLDivElement>(null);
  const q = query.trim().toLowerCase();
  const counts = useMemo(() => {
    const out: Record<Filter, number> = { all: 0, ok: 0, bad: 0, warn: 0, unknown: 0, info: 0 };
    for (const g of read.groups) for (const r of g.rows) {
      out.all += 1;
      out[r.state] += 1;
    }
    return out;
  }, [read]);

  useEffect(() => {
    if (!focusGroup) return;
    const el = bodyRef.current?.querySelector(`[data-group="${focusGroup}"]`);
    if (el && typeof (el as HTMLElement).scrollIntoView === 'function') {
      (el as HTMLElement).scrollIntoView({ block: 'start' });
    }
  }, [focusGroup]);

  return (
    <div className="sr-tab sr-tab--signals" data-testid="stock-read-signals">
      <p className="sr-summary">{readSummary(read)}</p>
      <div className="sr-filters" role="toolbar" aria-label="Filter signals">
        {FILTERS.filter(f => f.id === 'all' || counts[f.id] > 0).map(f => (
          <button
            key={f.id}
            type="button"
            className={`sr-chip sr-chip--${f.id}`}
            aria-pressed={filter === f.id}
            onClick={() => setFilter(f.id)}
            data-testid={`stock-read-filter-${f.id}`}
          >
            {f.label} {counts[f.id]}
          </button>
        ))}
        <input
          className="sr-search"
          type="search"
          placeholder="Search signals…"
          aria-label="Search signals"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.stopPropagation()}
          data-testid="stock-read-search"
        />
      </div>
      <div className="sr-groups" ref={bodyRef}>
        {read.groups.map(g => {
          const rows = g.rows.filter(r => (filter === 'all' || r.state === filter) && matches(r, q));
          if (rows.length === 0) return null;
          return (
            <section
              key={g.id}
              className={`sr-group${focusGroup === g.id ? ' sr-group--focus' : ''}`}
              data-group={g.id}
              data-testid={`stock-read-group-${g.id}`}
            >
              <GroupHead group={g} />
              <ReadRowList rows={rows} />
            </section>
          );
        })}
        {read.groups.every(g => !g.rows.some(r => (filter === 'all' || r.state === filter) && matches(r, q))) && (
          <p className="sr-empty">No signal matches.</p>
        )}
      </div>
    </div>
  );
}
