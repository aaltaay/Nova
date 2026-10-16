/**
 * The strip at the very bottom of the desk (operator ask, 2026-10-16): IBKR's four caps -- Level 1 quote lines,
 * Level 2 books, historical requests in IBKR's 10-minute window, Time & Sales lines -- each used of its cap with a
 * bar of its slots, amber from 80% and red when full; a cell's hover lists who uses it. Main window only. Read-only.
 */
import { novaFetch } from '../api/novaFetch';
import { CAPACITY_BOXES_MAX, CAPACITY_POLL_MS, CAPACITY_READ_TIMEOUT_MS } from './capacityConstants';
import { toneOf, useCapacity, type CapacityCell } from './capacityRead';
import './capacity.css';

interface Props {
  pollMs?: number;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

function Slots({ cell }: { cell: CapacityCell }) {
  const cap = cell.cap ?? Math.max(cell.used, 1);
  if (cap <= CAPACITY_BOXES_MAX) {
    return (
      <span className="nova-capacity__boxes" aria-hidden="true">
        {Array.from({ length: cap }, (_, i) => (
          <span key={i} className={`nova-capacity__box${i < cell.used ? ' nova-capacity__box--on' : ''}`} />
        ))}
      </span>
    );
  }
  const pct = Math.min(100, (cell.used / cap) * 100);
  return (
    <span className="nova-capacity__bar" aria-hidden="true">
      <span className="nova-capacity__fill" style={{ width: `${pct}%` }} />
    </span>
  );
}

function Cell({ label, cell, testId }: { label: string; cell: CapacityCell; testId: string }) {
  const count = cell.cap == null ? `${cell.used}` : `${cell.used} / ${cell.cap}`;
  const who = cell.users.length ? cell.users.map(([name, n]) => (n > 1 ? `${name}: ${n}` : name)).join('\n') : 'none in use';
  const title = `${label}: ${count}${cell.cap == null ? ' (IBKR has not said its cap)' : ''}${cell.note ? ` -- ${cell.note}` : ''}\n${who}`;
  return (
    <span className="nova-capacity__cell" data-tone={toneOf(cell)} title={title} data-testid={testId}>
      <span className="nova-capacity__label">{label}</span>
      <Slots cell={cell} />
      <span className="nova-capacity__count">{count}</span>
      {cell.note && cell.note.startsWith('next') && <span className="nova-capacity__note">{cell.note}</span>}
    </span>
  );
}

export function CapacityStrip({
  pollMs = CAPACITY_POLL_MS,
  fetchImpl = novaFetch,
  timeoutMs = CAPACITY_READ_TIMEOUT_MS,
}: Props = {}) {
  const read = useCapacity(pollMs, fetchImpl, timeoutMs);
  return (
    <div className="nova-capacity" role="status" aria-label="IBKR capacity" data-testid="capacity-strip">
      {read.state === 'loading' && <span className="nova-capacity__plain">Capacity: reading…</span>}
      {read.state === 'unread' && <span className="nova-capacity__plain">Capacity: not read -- {read.why}</span>}
      {read.state === 'ok' && (
        <>
          <Cell label="Level 1" cell={read.model.l1} testId="capacity-l1" />
          <Cell label="Level 2" cell={read.model.l2} testId="capacity-l2" />
          <Cell label="History" cell={read.model.history} testId="capacity-history" />
          <Cell label="Time & Sales" cell={read.model.tape} testId="capacity-tape" />
        </>
      )}
    </div>
  );
}
