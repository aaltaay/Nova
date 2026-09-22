/** Decision + snap tables for the HOD Momo debug panel. */
import { SelectableTableRow } from '../components/SelectableTableRow';
import { TICKER_OPEN_TRADER_TITLE } from '../constants';
import {
  fmtEnrichedAgo,
  fmtPctPoints,
  fmtTimes,
  fmtTs,
  fmtUsd,
  fmtVol,
  truncate,
} from './hodMomoDebugFormat';

export interface DebugDecisionRow {
  ts: number;
  symbol: string;
  price: number;
  rvol: number | null;
  gap_pct: number | null;
  change_pct: number | null;
  gate_blocked: string | null;
  strategies_fired: number[];
  would_fire: boolean;
}

export interface DebugSnapRow {
  symbol: string;
  price: number;
  rvol: number | null;
  float_shares: number | null;
  gap_pct: number | null;
  change_pct: number | null;
  volume: number | null;
  last_enriched: number;
}

interface NavProps {
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

export function RecentDecisionsTable({
  decisions,
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
}: { decisions: DebugDecisionRow[] } & NavProps) {
  return (
    <div className="dbg-card dbg-card-wide">
      <div className="dbg-card-title">Recent Decisions <span className="dbg-count-badge">{decisions.length}</span></div>
      <div className="dbg-table-wrap">
        <table className="dbg-table">
          <thead>
            <tr>
              <th>Time</th>
              <th title={TICKER_OPEN_TRADER_TITLE}>Symbol</th>
              <th>Price</th>
              <th>RVOL</th>
              <th>Gap%</th>
              <th>Chg%</th>
              <th>Gate</th>
              <th>Fired</th>
            </tr>
          </thead>
          <tbody>
            {decisions.length === 0 ? (
              <tr><td colSpan={8} className="dbg-empty">No decisions yet — trades seen but none past blocklist?</td></tr>
            ) : (
              decisions.map((d, i) => (
                <SelectableTableRow
                  key={`${d.symbol}-${d.ts}-${i}`}
                  symbol={d.symbol}
                  selected={selectedSymbol === d.symbol}
                  onSelect={onSelectSymbol}
                  onOpenTrading={onOpenTrading}
                  className={d.gate_blocked ? 'dbg-row-blocked' : d.would_fire ? 'dbg-row-fired' : 'dbg-row-pass'}
                >
                  <td className="dbg-mono">{fmtTs(d.ts)}</td>
                  <td className="dbg-sym">{d.symbol}</td>
                  <td className="dbg-mono">{fmtUsd(d.price)}</td>
                  <td className="dbg-mono">{fmtTimes(d.rvol)}</td>
                  <td className="dbg-mono">{fmtPctPoints(d.gap_pct)}</td>
                  <td className="dbg-mono">{fmtPctPoints(d.change_pct)}</td>
                  <td className="dbg-gate" title={d.gate_blocked || ''}>{d.gate_blocked ? truncate(d.gate_blocked, 28) : '✓ passed'}</td>
                  <td>{d.strategies_fired.length > 0 ? d.strategies_fired.join(',') : '—'}</td>
                </SelectableTableRow>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function SnapsTable({
  snaps,
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
}: { snaps: DebugSnapRow[] } & NavProps) {
  return (
    <div className="dbg-card dbg-card-wide">
      <div className="dbg-card-title">
        Recently Enriched Snapshots
        <span className="dbg-count-badge">{snaps.length}</span>
      </div>
      <div className="dbg-table-wrap">
        <table className="dbg-table">
          <thead>
            <tr>
              <th title={TICKER_OPEN_TRADER_TITLE}>Symbol</th>
              <th>Price</th>
              <th>RVOL</th>
              <th>Float</th>
              <th>Gap%</th>
              <th>Chg%</th>
              <th>Volume</th>
              <th>Enriched</th>
            </tr>
          </thead>
          <tbody>
            {snaps.length === 0 ? (
              <tr><td colSpan={8} className="dbg-empty">No enriched snaps yet — waiting for first enrichment cycle (~30s)</td></tr>
            ) : (
              snaps.map((s, i) => (
                <SelectableTableRow
                  key={`${s.symbol}-${i}`}
                  symbol={s.symbol}
                  selected={selectedSymbol === s.symbol}
                  onSelect={onSelectSymbol}
                  onOpenTrading={onOpenTrading}
                >
                  <td className="dbg-sym">{s.symbol}</td>
                  <td className="dbg-mono">{fmtUsd(s.price)}</td>
                  <td className="dbg-mono">{fmtTimes(s.rvol)}</td>
                  <td className="dbg-mono">{fmtVol(s.float_shares)}</td>
                  <td className="dbg-mono">{fmtPctPoints(s.gap_pct)}</td>
                  <td className={`dbg-mono ${s.change_pct != null && s.change_pct > 0 ? 'positive' : s.change_pct != null && s.change_pct < 0 ? 'negative' : ''}`}>
                    {fmtPctPoints(s.change_pct)}
                  </td>
                  <td className="dbg-mono">{fmtVol(s.volume)}</td>
                  <td className="dbg-mono">{fmtEnrichedAgo(s.last_enriched, Date.now() / 1000)}</td>
                </SelectableTableRow>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
