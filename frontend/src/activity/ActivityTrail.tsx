import { useState } from 'react';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import { formatActivityTime } from './formatActivity';
import {
  formatTrailKind,
  formatTrailMoney,
  formatTrailQty,
  formatTrailState,
  trailEventKey,
} from './formatTrail';
import type { TrailEvent, TrailItem } from './types';
import './activity.css';

/** When a trade happened: its close, else its open, else its first step (the Time cell). */
function trailWhen(item: TrailItem): number | null {
  const ts = item.closed_ts ?? item.opened_ts ?? item.events[0]?.ts;
  return ts != null && ts > 0 ? ts : null;
}

const COLUMNS: SortColumns<TrailItem> = {
  time: trailWhen,
  symbol: i => i.symbol,
  state: i => formatTrailState(i),
  side: i => i.side,
  qty: i => i.qty,
  pnl: i => i.pnl,
  commission: i => i.commission,
  steps: i => i.events.map(event => formatTrailKind(event.kind)).join(' -> '),
};

const EVENT_COLUMNS: SortColumns<TrailEvent> = {
  time: e => (e.ts != null && e.ts > 0 ? e.ts : null),
  step: e => formatTrailKind(e.kind),
  side: e => e.side,
  qty: e => e.qty,
  price: e => e.price,
  commission: e => e.commission,
  pnl: e => e.pnl,
};

interface Props {
  items: TrailItem[];
  loading?: boolean;
  error?: string | null;
  onRefresh?: () => void;
}

export function ActivityTrail({ items, loading = false, error = null, onRefresh }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const { rows: sorted, sort, onSort } = useTableSort('activity.trail', items, COLUMNS);

  return (
    <div className="activity-panel activity-trail" data-testid="activity-trail">
      <header className="activity-panel__header">
        <div>
          <p className="activity-panel__kicker">D-046 · local facts</p>
          <h2>Trail</h2>
          <p className="activity-panel__hint">
            Place, fill, flatten/close, and stored CommissionReport times. Reads
            journal + ledger only -- no Client Portal.
          </p>
        </div>
        {onRefresh && (
          <button type="button" className="ibkr-btn-secondary" onClick={onRefresh}>
            Refresh
          </button>
        )}
      </header>
      {loading && items.length === 0 && (
        <div className="ibkr-empty" role="status">Loading trail…</div>
      )}
      {error && (
        <div className="ibkr-empty ibkr-empty--error" data-testid="activity-trail-error">
          {error} -- showing last-known data.
        </div>
      )}
      {items.length === 0 && !loading && !error && (
        <div className="ibkr-empty" data-testid="activity-trail-empty">
          No closed trades or session activity yet.
        </div>
      )}
      {items.length > 0 && (
        <table className="ibkr-table ibkr-table--orders activity-table">
          <thead>
            <tr>
              <SortTh col="time" sort={sort} onSort={onSort}>Time</SortTh>
              <SortTh col="symbol" sort={sort} onSort={onSort}>Symbol</SortTh>
              <SortTh col="state" sort={sort} onSort={onSort}>State</SortTh>
              <SortTh col="side" sort={sort} onSort={onSort}>Side</SortTh>
              <SortTh col="qty" sort={sort} onSort={onSort}>Qty</SortTh>
              <SortTh col="pnl" sort={sort} onSort={onSort}>P/L</SortTh>
              <SortTh col="commission" sort={sort} onSort={onSort}>Commission</SortTh>
              <SortTh col="steps" sort={sort} onSort={onSort}>Steps</SortTh>
            </tr>
          </thead>
          <tbody>
            {sorted.map(item => {
              const open = expandedId === item.id;
              return (
                <TrailRows
                  key={item.id}
                  item={item}
                  open={open}
                  onToggle={() => setExpandedId(open ? null : item.id)}
                />
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

function TrailRows({
  item,
  open,
  onToggle,
}: {
  item: TrailItem;
  open: boolean;
  onToggle: () => void;
}) {
  const when = item.closed_ts ?? item.opened_ts ?? item.events[0]?.ts;
  return (
    <>
      <tr
        className={open ? 'activity-row activity-row--open' : 'activity-row'}
        data-testid={`activity-trail-row-${item.id}`}
        onClick={onToggle}
      >
        <td>{formatActivityTime(when)}</td>
        <td>{item.symbol || '--'}</td>
        <td>{formatTrailState(item)}</td>
        <td>{item.side || '--'}</td>
        <td>{formatTrailQty(item.qty)}</td>
        <td>{formatTrailMoney(item.pnl)}</td>
        <td>{formatTrailMoney(item.commission)}</td>
        <td>{item.events.map(event => formatTrailKind(event.kind)).join(' -> ')}</td>
      </tr>
      {open && (
        <tr className="activity-detail-row" data-testid={`activity-trail-detail-${item.id}`}>
          <td colSpan={8}>
            <TrailDetail item={item} />
          </td>
        </tr>
      )}
    </>
  );
}

function TrailDetail({ item }: { item: TrailItem }) {
  const { rows: events, sort, onSort } = useTableSort('activity.trail-steps', item.events, EVENT_COLUMNS);
  return (
    <div className="activity-detail">
      {item.close_key && <p>close_key {item.close_key}</p>}
      {item.notes && <p>{item.notes}</p>}
      <table className="ibkr-table activity-evidence">
        <thead>
          <tr>
            <SortTh col="time" sort={sort} onSort={onSort}>Time</SortTh>
            <SortTh col="step" sort={sort} onSort={onSort}>Step</SortTh>
            <SortTh col="side" sort={sort} onSort={onSort}>Side</SortTh>
            <SortTh col="qty" sort={sort} onSort={onSort}>Qty</SortTh>
            <SortTh col="price" sort={sort} onSort={onSort}>Price</SortTh>
            <SortTh col="commission" sort={sort} onSort={onSort}>Commission</SortTh>
            <SortTh col="pnl" sort={sort} onSort={onSort}>P/L</SortTh>
          </tr>
        </thead>
        <tbody>
          {events.map(event => {
            // Keyed by the step's place in the trade, so a sort moves rows rather than remounting them.
            const index = item.events.indexOf(event);
            return <TrailEventRow key={trailEventKey(event, index)} event={event} />;
          })}
        </tbody>
      </table>
    </div>
  );
}

function TrailEventRow({ event }: { event: TrailEvent }) {
  return (
    <tr>
      <td>{formatActivityTime(event.ts)}</td>
      <td>{formatTrailKind(event.kind)}</td>
      <td>{event.side || '--'}</td>
      <td>{formatTrailQty(event.qty)}</td>
      <td>{formatTrailMoney(event.price)}</td>
      <td>{formatTrailMoney(event.commission)}</td>
      <td>{formatTrailMoney(event.pnl)}</td>
    </tr>
  );
}