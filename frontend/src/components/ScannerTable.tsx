/** Dense scanner table: Gappers / Movers / After Hours tabs share this rendering. */
import { useMemo } from 'react';
import { ScannerTableRow } from './ScannerTableRow';
import { ScannerColGroup, ScannerRowNumHeader } from './ScannerTableChrome';
import { SCANNER_TABLE_WRAPPER_CLASS, scannerColClass } from './scannerTableCol';
import { isRowQuoteStale } from '../hooks/useScannerPriceStream';
import { SCANNER_VOLUME_COLUMN_LABEL } from '../constants';
import { SCANNER_HEADER_SHORT_LABEL, SCANNER_VOLUME_HEADER_TITLE } from '../constantGroups/scanner_board';
import type { ScannerRow, SortConfig } from '../types/scanner';

export { NewsCell } from './NewsCell';
export { WatchCell } from './ScannerTableRow';
export { ScannerColGroup, ScannerRowNumHeader, ScannerRowNumCell } from './ScannerTableChrome';

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

export function ScannerTable({
  columns, data, sortState, onSort, selectedSymbol, onSelect, onOpenTrading,
  pricesStale = false,
  flashSymbols = {},
  rowQuoteTs = {},
  nowSec = 0,
}: ScannerTableProps) {
  // The gap bar scales to the largest |gap| on the list (the top row when
  // sorted by gap). No gap anywhere: no bars, just the numbers.
  const gapScaleMax = useMemo(() => {
    let max = 0;
    for (const r of data) {
      if (r.gap_percent != null && Math.abs(r.gap_percent) > max) max = Math.abs(r.gap_percent);
    }
    return max > 0 ? max : null;
  }, [data]);
  return (
    <div className={SCANNER_TABLE_WRAPPER_CLASS}>
      <table>
        <ScannerColGroup columns={columns} />
        <thead>
          <tr>
            <ScannerRowNumHeader />
            {columns.map(([key, label]) => (
              <th
                key={key}
                data-col={key}
                className={`sortable-th ${scannerColClass(key)}`}
                onClick={() => onSort(key)}
                title={key === 'volume' ? SCANNER_VOLUME_HEADER_TITLE : label}
                aria-sort={
                  sortState.key === key
                    ? sortState.dir === 'asc' ? 'ascending' : 'descending'
                    : 'none'
                }
              >
                <span className="th-inner">
                  {/* Clipped labels read "NEW:" / "EARNIN" -- the label ellipsizes and the th title carries it. */}
                  <span className="th-label">
                    {key === 'volume' ? SCANNER_VOLUME_COLUMN_LABEL : SCANNER_HEADER_SHORT_LABEL[key] ?? label}
                  </span>
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
          {data.map((row, index) => {
            const sym = row.symbol.toUpperCase();
            return (
              <ScannerTableRow
                key={row.symbol}
                columns={columns}
                row={row}
                index={index}
                selected={selectedSymbol === row.symbol}
                onSelect={onSelect}
                onOpenTrading={onOpenTrading}
                flash={flashSymbols[sym]}
                stale={isRowQuoteStale(row.symbol, rowQuoteTs, nowSec, pricesStale)}
                gapScaleMax={gapScaleMax}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
