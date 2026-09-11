/** Dense scanner table: Gappers / Movers / After Hours tabs share this rendering. */
import { ScannerTableRow } from './ScannerTableRow';
import { ScannerRowNumHeader } from './ScannerTableChrome';
import { isRowQuoteStale } from '../hooks/useScannerPriceStream';
import {
  SCANNER_RVOL_SOURCE_TITLE,
  SCANNER_VOLUME_COLUMN_LABEL,
} from '../constants';
import type { ScannerRow, SortConfig } from '../types/scanner';

export { NewsCell } from './NewsCell';
export { WatchCell } from './ScannerTableRow';
export { ScannerRowNumHeader, ScannerRowNumCell } from './ScannerTableChrome';

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
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
