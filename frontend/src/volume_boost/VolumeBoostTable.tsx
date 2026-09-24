import { ScannerColGroup, ScannerRowNumCell, ScannerRowNumHeader } from '../components/ScannerTable';
import { SelectableTableRow } from '../components/SelectableTableRow';
import { SCANNER_TABLE_WRAPPER_CLASS, scannerColClass } from '../components/scannerTableCol';
import { SymbolSelectButton } from '../components/SymbolSelectButton';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import { fmtPrice, fmtVolume } from '../utils/quoteFormat';
import { VOLUME_BOOST_COLUMNS } from './constants';
import { formatSpikeAge } from './formatAge';
import type { VolumeBoostRow } from './types';

/** Keyed like VOLUME_BOOST_COLUMNS. Age starts with the newest spike; Status puts Hot above Cooling. */
const SORT_COLUMNS: SortColumns<VolumeBoostRow> = {
  symbol: r => r.symbol,
  price: r => r.price,
  spike_ratio: r => r.spike_ratio,
  spike_shares: r => r.spike_shares,
  age_sec: { value: r => r.age_sec, first: 'asc' },
  status: r => r.status === 'hot',
};

export function VolumeBoostTable({
  rows,
  selectedSymbol,
  onSelect,
  onOpenTrading,
}: {
  rows: VolumeBoostRow[];
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}) {
  const { rows: sorted, sort, onSort } = useTableSort('volume_boost.spikes', rows, SORT_COLUMNS);
  return (
    <div className={SCANNER_TABLE_WRAPPER_CLASS}>
      <table data-testid="volume-boost-table">
        <ScannerColGroup columns={VOLUME_BOOST_COLUMNS} />
        <thead>
          <tr>
            <ScannerRowNumHeader />
            {VOLUME_BOOST_COLUMNS.map(([key, label]) => (
              <SortTh key={key} col={key} sort={sort} onSort={onSort} data-col={key} className={scannerColClass(key)}>
                {label}
              </SortTh>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, index) => (
            <SelectableTableRow
              key={row.symbol}
              symbol={row.symbol}
              selected={selectedSymbol === row.symbol}
              onSelect={onSelect}
              onOpenTrading={onOpenTrading}
              openOnRowClick={false}
            >
              <ScannerRowNumCell index={index} />
              <td data-col="symbol" className={scannerColClass('symbol')}>
                <SymbolSelectButton
                  symbol={row.symbol}
                  selected={selectedSymbol === row.symbol}
                  onSelect={onSelect}
                  onOpenTrading={onOpenTrading}
                />
              </td>
              <td data-col="price" className={scannerColClass('price')}>{fmtPrice(row.price)}</td>
              <td data-col="spike_ratio" className={`${scannerColClass('spike_ratio')} volume-boost-ratio`}>
                {row.spike_ratio != null ? `${row.spike_ratio.toFixed(1)}x` : '--'}
              </td>
              <td data-col="spike_shares" className={scannerColClass('spike_shares')}>
                {fmtVolume(row.spike_shares)}
              </td>
              <td data-col="age_sec" className={scannerColClass('age_sec')}>
                {formatSpikeAge(row.age_sec)}
              </td>
              <td data-col="status" className={scannerColClass('status')}>
                <span
                  className={`volume-boost-status volume-boost-status--${row.status}`}
                >
                  {row.status === 'cooling' ? 'Cooling' : 'Hot'}
                </span>
              </td>
            </SelectableTableRow>
          ))}
        </tbody>
      </table>
    </div>
  );
}
