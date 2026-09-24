/** The sheet's Decisions tab: one symbol's day as the bot saw it -- every lane's legs, refusals, arms
 * and triggers from the eyes' journal, HOD Momo's first alerts, borrow changes, news, the open and
 * the high of day, and the bot's own lines -- each one a click away on the 1-minute chart. */
import { useMemo, useState } from 'react';
import { LANE_LABELS } from './constants';
import { setupName } from './planMath';
import { hhmmEt, hhmmssEt } from './timeWords';
import type { DecisionEvent, ReadState, StockDecisions } from './types';
import type { PolledState } from './useStockRead';

const LANES: { id: string; label: string }[] = [
  { id: 'all', label: 'All lanes' },
  { id: 'first_pullback', label: 'First pullback' },
  { id: 'bull_flag', label: 'Bull flag' },
  { id: 'flat_top_breakout', label: 'Flat top' },
  { id: 'red_to_green', label: 'Red to green' },
  { id: 'hod_momo', label: 'HOD Momo' },
  { id: 'market', label: 'Market' },
  { id: 'bot', label: 'Bot' },
];

/** What an event says for a long trade, for its dot. */
export function eventTone(e: DecisionEvent): ReadState {
  if (e.lane === 'bot') return 'warn';
  switch (e.event) {
    case 'armed':
    case 'rearmed':
    case 'near':
    case 'triggered':
    case 'alert':
      return 'ok';
    case 'failed':
    case 'disarmed':
      return 'bad';
    case 'filtered':
      return 'warn';
    case 'tape':
      return /GO$/.test(e.title) ? 'ok' : /VETO/.test(e.title) ? 'bad' : 'warn';
    case 'state':
      if (/^(Not armed|Dropped)/.test(e.title)) return 'bad';
      return /^Forming/.test(e.title) ? 'warn' : 'unknown';
    case 'leg':
      return 'info';
    case 'news':
      return /\(negative/.test(e.title) ? 'bad' : 'ok';
    default:
      return 'unknown';
  }
}

function clock(ts: number): string {
  return Math.round(ts) % 60 === 0 ? hhmmEt(ts) : hhmmssEt(ts);
}

export function DecisionsTab({
  state,
  onShow,
}: {
  state: PolledState<StockDecisions>;
  onShow: (e: DecisionEvent) => void;
}) {
  const [lane, setLane] = useState('all');
  const d = state.data;
  const events = useMemo(() => (d ? d.events.filter(e => lane === 'all' || e.lane === lane) : []), [d, lane]);
  if (!d) {
    return (
      <div className="sr-tab" data-testid="stock-read-decisions">
        <p className="sr-empty">{state.error ?? (state.unavailable ? 'This backend has no decisions read yet: reload it.' : 'Reading the day…')}</p>
      </div>
    );
  }
  const present = new Set(d.events.map(e => e.lane));
  const failed = Object.entries(d.sources).filter(([, s]) => !s.ok);
  return (
    <div className="sr-tab sr-tab--decisions" data-testid="stock-read-decisions">
      <p className="sr-summary">{d.summary.text}</p>
      <div className="sr-filters" role="toolbar" aria-label="Filter lanes">
        {LANES.filter(l => l.id === 'all' || present.has(l.id)).map(l => (
          <button
            key={l.id}
            type="button"
            className="sr-chip"
            aria-pressed={lane === l.id}
            onClick={() => setLane(l.id)}
            data-testid={`stock-read-lane-${l.id}`}
          >
            {l.label}
          </button>
        ))}
      </div>
      {events.length === 0 && <p className="sr-empty">Nothing on file for this lane today.</p>}
      <ol className="sr-events">
        {events.map((e, i) => (
          <li key={`${e.ts}-${e.lane}-${i}`} className={`sr-event sr-row--${eventTone(e)}`} data-testid="stock-read-event">
            <span className="sr-event__time">{clock(e.ts)}</span>
            <span className="sr-dot" aria-hidden="true" />
            <span className={`sr-lane sr-lane--${e.lane}`} title={setupName(e.lane)}>{LANE_LABELS[e.lane] ?? e.lane}</span>
            <span className="sr-event__title">
              {e.title}
              {e.count > 1 && (
                <span className="sr-event__count"> ×{e.count}{e.last_ts ? ` to ${clock(e.last_ts)}` : ''}</span>
              )}
            </span>
            <button type="button" className="sr-link sr-event__show" onClick={() => onShow(e)}>
              show on chart ›
            </button>
            {e.detail && <span className="sr-event__detail">{e.detail}</span>}
          </li>
        ))}
      </ol>
      {failed.length > 0 && (
        <p className="sr-note" data-testid="stock-read-sources-failed">
          Not read: {failed.map(([k, s]) => `${k}${s.error ? ` (${s.error})` : ''}`).join('; ')}.
        </p>
      )}
    </div>
  );
}
