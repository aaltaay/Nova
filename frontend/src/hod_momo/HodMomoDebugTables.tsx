/** Decision + snap tables for the HOD Momo debug panel. */
import { SelectableTableRow } from '../components/SelectableTableRow';
import { TICKER_OPEN_TRADER_TITLE } from '../constants';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
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

/** Newest first on Time; Gate groups the block reasons (passed rows have none and sit last). */
const DECISION_COLUMNS: SortColumns<DebugDecisionRow> = {
  time: d => d.ts,
  symbol: d => d.symbol,
  price: d => d.price,
  rvol: d => d.rvol,
  gap: d => d.gap_pct,
  chg: d => d.change_pct,
  gate: d => d.gate_blocked,
  fired: d => d.strategies_fired.length,
};

/** Enriched sorts the newest enrichment first; a snap never enriched (0) has no time. */
const SNAP_COLUMNS: SortColumns<DebugSnapRow> = {
  symbol: s => s.symbol,
  price: s => s.price,
  rvol: s => s.rvol,
  float: s => s.float_shares,
  gap: s => s.gap_pct,
  chg: s => s.change_pct,
  volume: s => s.volume,
  enriched: s => (s.last_enriched > 0 ? s.last_enriched : null),
};

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
  const { rows: sorted, sort, onSort } = useTableSort('hod_momo.debug_decisions', decisions, DECISION_COLUMNS);
  return (
    <div className="dbg-card dbg-card-wide">
      <div className="dbg-card-title">Recent Decisions <span className="dbg-count-badge">{decisions.length}</span></div>
      <div className="dbg-table-wrap">
        <table className="dbg-table">
          <thead>
            <tr>
              <SortTh col="time" sort={sort} onSort={onSort}>Time</SortTh>
              <SortTh col="symbol" sort={sort} onSort={onSort} title={TICKER_OPEN_TRADER_TITLE}>Symbol</SortTh>
              <SortTh col="price" sort={sort} onSort={onSort}>Price</SortTh>
              <SortTh col="rvol" sort={sort} onSort={onSort}>RVOL</SortTh>
              <SortTh col="gap" sort={sort} onSort={onSort}>Gap%</SortTh>
              <SortTh col="chg" sort={sort} onSort={onSort}>Chg%</SortTh>
              <SortTh col="gate" sort={sort} onSort={onSort}>Gate</SortTh>
              <SortTh col="fired" sort={sort} onSort={onSort}>Fired</SortTh>
            </tr>
          </thead>
          <tbody>
            {decisions.length === 0 ? (
              <tr><td colSpan={8} className="dbg-empty">No decisions yet — trades seen but none past blocklist?</td></tr>
            ) : (
              sorted.map((d, i) => (
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
  const { rows: sorted, sort, onSort } = useTableSort('hod_momo.debug_snaps', snaps, SNAP_COLUMNS);
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
              <SortTh col="symbol" sort={sort} onSort={onSort} title={TICKER_OPEN_TRADER_TITLE}>Symbol</SortTh>
              <SortTh col="price" sort={sort} onSort={onSort}>Price</SortTh>
              <SortTh col="rvol" sort={sort} onSort={onSort}>RVOL</SortTh>
              <SortTh col="float" sort={sort} onSort={onSort}>Float</SortTh>
              <SortTh col="gap" sort={sort} onSort={onSort}>Gap%</SortTh>
              <SortTh col="chg" sort={sort} onSort={onSort}>Chg%</SortTh>
              <SortTh col="volume" sort={sort} onSort={onSort}>Volume</SortTh>
              <SortTh col="enriched" sort={sort} onSort={onSort}>Enriched</SortTh>
            </tr>
          </thead>
          <tbody>
            {snaps.length === 0 ? (
              <tr><td colSpan={8} className="dbg-empty">No enriched snaps yet — waiting for first enrichment cycle (~30s)</td></tr>
            ) : (
              sorted.map((s, i) => (
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
