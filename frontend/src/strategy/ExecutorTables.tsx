/** Staged tickets + open positions tables for the Automation panel. */
import { useEffect, useState } from 'react';
import { SelectableTableRow } from '../components/SelectableTableRow';
import { NOVA_OS_CONFIRM_TIMEOUT_SEC, SETUP_LABELS } from '../constants';
import { formatShareQty } from '../utils/formatShareQty';
import type { ExecutorOpenPosition, ExecutorStagedTicket } from './types';

function fmtPrice(v: number): string {
  return `$${v.toFixed(2)}`;
}

function fmtTime(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
  });
}

function Countdown({ expiresAt }: { expiresAt: number }) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), 500);
    return () => clearInterval(id);
  }, []);
  const left = Math.max(0, Math.ceil(expiresAt - now));
  return <span className={left <= 10 ? 'nova-os-decision-nobuy' : ''}>{left}s</span>;
}

export function StagedTable({
  tickets,
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
  onApprove,
  onReject,
}: {
  tickets: ExecutorStagedTicket[];
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}) {
  if (tickets.length === 0) {
    return <div className="empty-state">No staged tickets. Raise mode to Confirm to stage BUY decisions.</div>;
  }
  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th title="Click: Quote Panel · Double-click: Trader">Symbol</th>
            <th>Setup</th>
            <th>Entry</th>
            <th>Stop</th>
            <th>Target</th>
            <th>Shares</th>
            <th title={`Expires after ${NOVA_OS_CONFIRM_TIMEOUT_SEC}s`}>TTL</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <SelectableTableRow
              key={t.id}
              symbol={t.symbol}
              selected={selectedSymbol === t.symbol}
              onSelect={onSelectSymbol}
              onOpenTrading={onOpenTrading}
            >
              <td>{t.symbol}</td>
              <td><span className="pillar-chip pillar-pass">{SETUP_LABELS[t.setup] ?? t.setup}</span></td>
              <td>{fmtPrice(t.entry)}</td>
              <td>{fmtPrice(t.stop)}</td>
              <td>{fmtPrice(t.target)}</td>
              <td>{formatShareQty(t.shares)}</td>
              <td><Countdown expiresAt={t.expires_at} /></td>
              <td className="nova-os-staged-actions">
                <button
                  type="button"
                  className="executor-arm-btn"
                  onClick={(e) => { e.stopPropagation(); onApprove(t.id); }}
                >
                  Approve
                </button>
                <button
                  type="button"
                  className="executor-disarm-btn"
                  onClick={(e) => { e.stopPropagation(); onReject(t.id); }}
                >
                  Reject
                </button>
              </td>
            </SelectableTableRow>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function OpenPositionsTable({
  positions,
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
  onCancel,
}: {
  positions: ExecutorOpenPosition[];
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  onCancel: (symbol: string) => void;
}) {
  if (positions.length === 0) {
    return <div className="empty-state">No open automated positions right now.</div>;
  }
  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Opened</th>
            <th title="Click: Quote Panel · Double-click: Trader">Symbol</th>
            <th>Setup</th>
            <th>Qty</th>
            <th>Entry</th>
            <th>Stop</th>
            <th>Target</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <SelectableTableRow
              key={p.symbol}
              symbol={p.symbol}
              selected={selectedSymbol === p.symbol}
              onSelect={onSelectSymbol}
              onOpenTrading={onOpenTrading}
            >
              <td className="hod-time-cell">{fmtTime(p.opened_ts)}</td>
              <td>{p.symbol}</td>
              <td><span className="pillar-chip pillar-pass">{SETUP_LABELS[p.setup] ?? p.setup}</span></td>
              <td>{formatShareQty(p.qty)}</td>
              <td>{fmtPrice(p.entry_price)}</td>
              <td>{fmtPrice(p.stop_price)}</td>
              <td>{fmtPrice(p.target_price)}</td>
              <td>
                <button
                  type="button"
                  className="executor-disarm-btn"
                  title="Cancel only if the entry parent is still unfilled. Does not remove a protective stop on a filled position."
                  onClick={(e) => { e.stopPropagation(); onCancel(p.symbol); }}
                >
                  Cancel entry
                </button>
              </td>
            </SelectableTableRow>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export { fmtPrice };
