import { useEffect, useState } from 'react';
import {
  formatActivityOrderRef,
  formatActivityQty,
  formatActivityTime,
  formatTimingMs,
} from './formatActivity';
import { fetchActivityDetail } from './useActivityLedger';
import type { ActivityDetail, ActivityRow } from './types';
import './activity.css';

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
              <th>Time</th>
              <th>Symbol</th>
              <th>Op</th>
              <th>Source</th>
              <th>Side</th>
              <th>Qty</th>
              <th>Order</th>
              <th>Status</th>
              <th>Ack</th>
              <th>1-share</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => {
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
              <th>Provenance</th>
              <th>Leg</th>
              <th>State</th>
              <th>Shares</th>
              <th>Price</th>
              <th>Slip / sh</th>
            </tr>
          </thead>
          <tbody>
            {evidence.map((item, index) => (
              <tr key={`${item.provenance || 'ev'}-${index}`}>
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
