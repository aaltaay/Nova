import { useEffect, useState } from 'react';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import {
  formatActivityOrderRef,
  formatActivityQty,
  formatActivityTime,
  formatTimingMs,
} from './formatActivity';
import { fetchActivityDetail } from './useActivityLedger';
import type { ActivityDetail, ActivityFillEvidence, ActivityRow } from './types';
import './activity.css';

/** A positive id as a number, else null (the Order cell's own rule). */
function positiveId(id: number | null | undefined): number | null {
  const n = Number(id);
  return Number.isFinite(n) && n > 0 ? Math.trunc(n) : null;
}

const COLUMNS: SortColumns<ActivityRow> = {
  time: r => (r.created_ts > 0 ? r.created_ts : null),
  symbol: r => r.symbol,
  op: r => r.operation,
  source: r => r.source,
  side: r => r.side,
  // The quantity that went to the broker; the request when nothing was sent.
  qty: r => r.sent_qty ?? r.requested_qty,
  order: r => positiveId(r.order_id) ?? positiveId(r.perm_id),
  status: r => r.broker_status || r.status,
  ack: r => r.timings?.broker_ack_ms,
  one_share: r => r.forced_one_share,
};

const EVIDENCE_COLUMNS: SortColumns<ActivityFillEvidence> = {
  provenance: e => e.provenance,
  leg: e => e.leg_role,
  state: e => e.fill_state,
  shares: e => e.shares,
  price: e => e.average_fill_price ?? e.price,
  slip: e => e.slippage_per_share,
};

interface Props {
  rows: ActivityRow[];
  loading?: boolean;
  error?: string | null;
  onRefresh?: () => void;
}

export function ActivityPanel({ rows, loading = false, error = null, onRefresh }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ActivityDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const { rows: sorted, sort, onSort } = useTableSort('activity.ledger', rows, COLUMNS);

  useEffect(() => {
    if (!expandedId) {
      setDetail(null);
      setDetailError(null);
      return;
    }
    let active = true;
    setDetailError(null);
    void fetchActivityDetail(expandedId)
      .then(row => {
        if (active) setDetail(row);
      })
      .catch(err => {
        if (active) {
          setDetail(null);
          setDetailError(err instanceof Error ? err.message : 'detail failed');
        }
      });
    return () => {
      active = false;
    };
  }, [expandedId]);

  return (
    <div className="activity-panel" data-testid="activity-panel">
      <header className="activity-panel__header">
        <div>
          <p className="activity-panel__kicker">ADR 007 · read-only ledger</p>
          <h2>Activity</h2>
          <p className="activity-panel__hint">
            Requested vs sent qty, spend gates, and permId. Closed-trade steps
            live in Trail above. This view never sends an order.
          </p>
        </div>
        {onRefresh && (
          <button type="button" className="ibkr-btn-secondary" onClick={onRefresh}>
            Refresh
          </button>
        )}
      </header>
      {loading && rows.length === 0 && (
        <div className="ibkr-empty" role="status">Loading ledger…</div>
      )}
      {error && (
        <div className="ibkr-empty ibkr-empty--error" data-testid="activity-error">
          {error} -- showing last-known data.
        </div>
      )}
      {rows.length === 0 && !loading && !error && (
        <div className="ibkr-empty">No execution rows in the ledger yet.</div>
      )}
      {rows.length > 0 && (
        <table className="ibkr-table ibkr-table--orders activity-table">
          <thead>
            <tr>
              <SortTh col="time" sort={sort} onSort={onSort}>Time</SortTh>
              <SortTh col="symbol" sort={sort} onSort={onSort}>Symbol</SortTh>
              <SortTh col="op" sort={sort} onSort={onSort}>Op</SortTh>
              <SortTh col="source" sort={sort} onSort={onSort}>Source</SortTh>
              <SortTh col="side" sort={sort} onSort={onSort}>Side</SortTh>
              <SortTh col="qty" sort={sort} onSort={onSort}>Qty</SortTh>
              <SortTh col="order" sort={sort} onSort={onSort}>Order</SortTh>
              <SortTh col="status" sort={sort} onSort={onSort}>Status</SortTh>
              <SortTh col="ack" sort={sort} onSort={onSort}>Ack</SortTh>
              <SortTh col="one_share" sort={sort} onSort={onSort}>1-share</SortTh>
            </tr>
          </thead>
          <tbody>
            {sorted.map(row => {
              const open = expandedId === row.id;
              return (
                <ActivityRows
                  key={row.id}
                  row={row}
                  open={open}
                  detail={open ? detail : null}
                  detailError={open ? detailError : null}
                  onToggle={() => setExpandedId(open ? null : row.id)}
                />
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

function ActivityRows({
  row,
  open,
  detail,
  detailError,
  onToggle,
}: {
  row: ActivityRow;
  open: boolean;
  detail: ActivityDetail | null;
  detailError: string | null;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        className={open ? 'activity-row activity-row--open' : 'activity-row'}
        data-testid={`activity-row-${row.id}`}
        onClick={onToggle}
      >
        <td>{formatActivityTime(row.created_ts)}</td>
        <td>{row.symbol || '--'}</td>
        <td>{row.operation}</td>
        <td>{row.source}</td>
        <td>{row.side || '--'}</td>
        <td title={row.forced_one_share ? 'IBKR_FORCE_ONE_SHARE clamped sent qty' : undefined}>
          {formatActivityQty(row)}
        </td>
        <td>{formatActivityOrderRef(row)}</td>
        <td>{row.broker_status || row.status}</td>
        <td>{formatTimingMs(row.timings?.broker_ack_ms)}</td>
        <td>{row.forced_one_share ? 'yes' : '--'}</td>
      </tr>
      {open && (
        <tr className="activity-detail-row" data-testid={`activity-detail-${row.id}`}>
          <td colSpan={10}>
            <ActivityDetailBody row={row} detail={detail} detailError={detailError} />
          </td>
        </tr>
      )}
    </>
  );
}

function ActivityDetailBody({
  row,
  detail,
  detailError,
}: {
  row: ActivityRow;
  detail: ActivityDetail | null;
  detailError: string | null;
}) {
  const evidence = detail?.fill_evidence ?? [];
  const { rows: sortedEvidence, sort, onSort } = useTableSort('activity.evidence', evidence, EVIDENCE_COLUMNS);
  return (
    <div className="activity-detail">
      <p>
        id {row.id}
        {row.perm_id ? ` · permId ${row.perm_id}` : ''}
        {row.mode ? ` · ${row.mode}` : ''}
        {row.gateway_mode ? ` · gateway ${row.gateway_mode}` : ''}
      </p>
      <p>
        gates: orders {String(row.orders_enabled)} · live confirm{' '}
        {String(row.live_trading_confirmed)} · short {String(row.short_enabled)}
      </p>
      {row.error && <p className="activity-detail__error">{row.error}</p>}
      {detailError && <p className="activity-detail__error">{detailError}</p>}
      {evidence.length === 0 && !detailError && <p>No fill evidence on this row.</p>}
      {evidence.length > 0 && (
        <table className="ibkr-table activity-evidence">
          <thead>
            <tr>
              <SortTh col="provenance" sort={sort} onSort={onSort}>Provenance</SortTh>
              <SortTh col="leg" sort={sort} onSort={onSort}>Leg</SortTh>
              <SortTh col="state" sort={sort} onSort={onSort}>State</SortTh>
              <SortTh col="shares" sort={sort} onSort={onSort}>Shares</SortTh>
              <SortTh col="price" sort={sort} onSort={onSort}>Price</SortTh>
              <SortTh col="slip" sort={sort} onSort={onSort}>Slip / sh</SortTh>
            </tr>
          </thead>
          <tbody>
            {sortedEvidence.map(item => (
              <tr key={`${item.provenance || 'ev'}-${evidence.indexOf(item)}`}>
                <td>{item.provenance || '--'}</td>
                <td>{item.leg_role || '--'}</td>
                <td>{item.fill_state || '--'}</td>
                <td>{item.shares ?? '--'}</td>
                <td>{item.average_fill_price ?? item.price ?? '--'}</td>
                <td>{item.slippage_per_share ?? '--'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
