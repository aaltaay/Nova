/** Dense scanner table: Gappers / Movers / After Hours tabs share this rendering. */
import React from 'react';
import { SymbolSelectButton } from './SymbolSelectButton';
import { SelectableTableRow } from './SelectableTableRow';
import { ScannerPriceCell } from './ScannerPriceCell';
import { NewsCell } from './NewsCell';
import { EarningsDots } from './EarningsDots';
import { isRowQuoteStale } from '../hooks/useScannerPriceStream';
import { fmtMarketCap, fmtPct, fmtPrice, fmtVolume } from '../utils/quoteFormat';
import {
  SCANNER_ROW_NUM_LABEL,
  SCANNER_ROW_NUM_TITLE,
  SCANNER_RVOL_SOURCE_BADGE,
  SCANNER_RVOL_SOURCE_TITLE,
  SCANNER_VOLUME_COLUMN_LABEL,
} from '../constants';
import type { ScannerRow, SortConfig } from '../types/scanner';
import type { WatchlistEntry } from '../strategy/types';

export { NewsCell } from './NewsCell';

/** Compact Five Pillars checkmark + composite score, joined from the Watchlist tab's
 * own scoring (see strategy/useWatchlistOverlay.ts). Null when the symbol isn't
 * currently ranked (e.g. outside the top WATCHLIST_MAX_ROWS candidates). */
export function WatchCell({ watchlist }: { watchlist: WatchlistEntry | null | undefined }) {
  if (!watchlist) return <span className="na-muted">—</span>;
  const { five_pillars, composite_score } = watchlist;
  const failing = five_pillars.pillars.filter(p => !p.passed).map(p => p.name.replace('_', ' '));
  const title = `${five_pillars.pass_count}/${five_pillars.total} pillars pass` +
    (failing.length ? ` (failing: ${failing.join(', ')})` : ' — all pass') +
    ` · composite score ${composite_score.toFixed(0)}/100`;
  return (
    <span className="cell-stack" title={title}>
      <span className={`cell-stack-primary ${five_pillars.all_pass ? 'positive' : 'na-muted'}`}>
        {five_pillars.checkmark}
      </span>
      <span className="cell-stack-secondary">{composite_score.toFixed(0)} pts</span>
    </span>
  );
}

interface ScannerTableProps {
  columns: [string, string][];
  data: ScannerRow[];
  sortState: SortConfig;
  onSort: (key: string) => void;
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  /** When true, tint price cells — table refresh is late / skipped. */
  pricesStale?: boolean;
  /** Per-symbol up/down flash from the latest L1 price patch. */
  flashSymbols?: Record<string, 'up' | 'down'>;
  /** Per-symbol last IB quote timestamp (unix seconds). */
  rowQuoteTs?: Record<string, number>;
  /** Current clock (unix seconds) for per-row stale tint. */
  nowSec?: number;
}

function fmtChangeAbs(v: number | null | undefined): string {
  if (v == null) return '—';
  return `${v >= 0 ? '+' : '-'}$${Math.abs(v).toFixed(2)}`;
}

function renderCell(
  key: string,
  row: ScannerRow,
  pricesStale: boolean,
  flashSymbols: Record<string, 'up' | 'down'>,
  rowQuoteTs: Record<string, number>,
  nowSec: number,
): React.ReactNode {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const anyRow = row as any;
  switch (key) {
    case 'symbol':
      return null; // handled as the symbol button in the row
    case 'price':
      return (
        <ScannerPriceCell
          symbol={row.symbol}
          price={row.price ?? anyRow.current_price}
          flash={flashSymbols[row.symbol.toUpperCase()]}
          stale={isRowQuoteStale(row.symbol, rowQuoteTs, nowSec, pricesStale)}
        />
      );
    case 'prev_close':
      return fmtPrice(row.prev_close ?? anyRow.previous_close);
    case 'change_pct':
      return (
        <span className="cell-stack">
          <span className={`cell-stack-primary ${row.change_pct != null && row.change_pct >= 0 ? 'positive' : 'negative'}`}>
            {fmtPct(row.change_pct)}
          </span>
          <span className="cell-stack-secondary">{fmtChangeAbs(row.change_abs)}</span>
        </span>
      );
    case 'gap_percent':
      return (
        <span className={row.gap_percent != null && row.gap_percent >= 0 ? 'positive' : row.gap_percent != null ? 'negative' : ''}>
          {fmtPct(row.gap_percent)}
        </span>
      );
    case 'volume':
      return (
        <span className="cell-stack" title={SCANNER_RVOL_SOURCE_TITLE}>
          <span className="cell-stack-primary">{fmtVolume(row.volume)}</span>
          <span className="cell-stack-secondary">
            {row.rel_volume != null ? (
              <>
                {row.rel_volume}x rel{' '}
                <span className="rvol-source-badge" title={SCANNER_RVOL_SOURCE_TITLE}>
                  {SCANNER_RVOL_SOURCE_BADGE}
                </span>
              </>
            ) : (
              <span className="na-muted">N/A</span>
            )}
          </span>
        </span>
      );
    case 'newest_headline_at':
      return <NewsCell newest_headline_at={row.newest_headline_at} />;
    case 'earnings_day_offset':
      return (
        <EarningsDots
          offset={row.earnings_day_offset}
          earningsDate={row.earnings_date}
          session={row.earnings_session}
          estimated={row.earnings_estimated}
        />
      );
    case 'watchlist_score':
      return <WatchCell watchlist={row.watchlist} />;
    case 'market_cap':
      return row.market_cap != null ? fmtMarketCap(row.market_cap) : <span className="na-muted">—</span>;
    case 'float':
      return row.float != null ? fmtVolume(row.float) : <span className="na-muted">—</span>;
    case 'short_interest':
      return (
        <span className="cell-stack">
          <span className="cell-stack-primary">
            {row.short_interest != null ? fmtVolume(row.short_interest) : <span className="na-muted">—</span>}
          </span>
          <span className="cell-stack-secondary">
            {row.short_ratio != null ? `${row.short_ratio.toFixed(1)}x ratio` : <span className="na-muted">N/A</span>}
          </span>
        </span>
      );
    // ── Large Cap swing table only (ADR 014) ──────────────────────────────────
    case 'rvol':
      return row.rvol != null ? (
        <span className={row.rvol >= 2 ? 'positive' : ''}>{row.rvol.toFixed(1)}x</span>
      ) : <span className="na-muted">—</span>;
    case 'atr_expansion':
      return row.atr_expansion != null ? (
        <span className={row.atr_expansion >= 1 ? 'positive' : ''}>{row.atr_expansion.toFixed(1)}x</span>
      ) : <span className="na-muted">—</span>;
    case 'change_5d_pct':
      return <span className={pctClass(row.change_5d_pct)}>{fmtPct(row.change_5d_pct ?? null)}</span>;
    case 'change_20d_pct':
      return <span className={pctClass(row.change_20d_pct)}>{fmtPct(row.change_20d_pct ?? null)}</span>;
    case 'high_20d':
      return (
        <span className="cell-stack">
          <span className="cell-stack-primary">
            {row.high_20d != null ? fmtPrice(row.high_20d) : <span className="na-muted">—</span>}
          </span>
          <span className="cell-stack-secondary">
            {row.low_20d != null ? fmtPrice(row.low_20d) : <span className="na-muted">—</span>}
          </span>
        </span>
      );
    case 'large_cap_score':
      return row.large_cap_score != null ? (
        <span title={
          row.score_completeness != null
            ? `${Math.round(row.score_completeness * 100)}% of signals present`
            : undefined
        }>
          {row.large_cap_score.toFixed(0)}
        </span>
      ) : <span className="na-muted">—</span>;
    case 'days_to_earnings':
      return row.days_to_earnings != null ? (
        <span className={row.days_to_earnings <= 7 ? 'negative' : ''}>
          {row.days_to_earnings}d
        </span>
      ) : <span className="na-muted">—</span>;
    default:
      return <span className="na-muted">—</span>;
  }
}

function pctClass(v: number | null | undefined): string {
  if (v == null) return '';
  return v >= 0 ? 'positive' : 'negative';
}

/** Non-sortable display-index column shared by scanner tables (not HOD/Running Up). */
export function ScannerRowNumHeader() {
  return (
    <th className="scanner-row-num-th" title={SCANNER_ROW_NUM_TITLE} aria-sort="none">
      {SCANNER_ROW_NUM_LABEL}
    </th>
  );
}

export function ScannerRowNumCell({ index }: { index: number }) {
  return (
    <td className="scanner-row-num" aria-label={`Row ${index + 1}`}>
      {index + 1}
    </td>
  );
}

export function ScannerTable({
  columns, data, sortState, onSort, selectedSymbol, onSelect, onOpenTrading,
  pricesStale = false,
  flashSymbols = {},
  rowQuoteTs = {},
  nowSec = 0,
}: ScannerTableProps) {
  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <ScannerRowNumHeader />
            {columns.map(([key, label]) => (
              <th
                key={key}
                className="sortable-th"
                onClick={() => onSort(key)}
                title={key === 'volume' ? SCANNER_RVOL_SOURCE_TITLE : undefined}
                aria-sort={
                  sortState.key === key
                    ? sortState.dir === 'asc' ? 'ascending' : 'descending'
                    : 'none'
                }
              >
                <span className="th-inner">
                  {key === 'volume' ? SCANNER_VOLUME_COLUMN_LABEL : label}
                  <span className={`sort-arrow${sortState.key === key ? ' active' : ''}`}>
                    {sortState.key === key
                      ? sortState.dir === 'asc' ? '↑' : '↓'
                      : '↕'}
                  </span>
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, index) => (
            <SelectableTableRow
              key={row.symbol}
              symbol={row.symbol}
              selected={selectedSymbol === row.symbol}
              onSelect={onSelect}
              onOpenTrading={onOpenTrading}
              openOnRowClick={false}
            >
              <ScannerRowNumCell index={index} />
              {columns.map(([key]) =>
                key === 'symbol' ? (
                  <td key={key}>
                    <SymbolSelectButton
                      symbol={row.symbol}
                      exchange={row.exchange}
                      selected={selectedSymbol === row.symbol}
                      onSelect={onSelect}
                      onOpenTrading={onOpenTrading}
                    />
                  </td>
                ) : (
                  <td key={key}>
                    {renderCell(key, row, pricesStale, flashSymbols, rowQuoteTs, nowSec)}
                  </td>
                )
              )}
            </SelectableTableRow>
          ))}
        </tbody>
      </table>
    </div>
  );
}
