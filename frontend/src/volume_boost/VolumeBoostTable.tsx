import { ScannerColGroup, ScannerRowNumCell, ScannerRowNumHeader } from '../components/ScannerTable';
import { SelectableTableRow } from '../components/SelectableTableRow';
import { SCANNER_TABLE_WRAPPER_CLASS, scannerColClass } from '../components/scannerTableCol';
import { SymbolSelectButton } from '../components/SymbolSelectButton';
import { fmtPrice, fmtVolume } from '../utils/quoteFormat';
import { VOLUME_BOOST_COLUMNS } from './constants';
import { formatSpikeAge } from './formatAge';
import type { VolumeBoostRow } from './types';

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
  return (
    <div className={SCANNER_TABLE_WRAPPER_CLASS}>
      <table data-testid="volume-boost-table">
        <ScannerColGroup columns={VOLUME_BOOST_COLUMNS} />
        <thead>
          <tr>
            <ScannerRowNumHeader />
            {VOLUME_BOOST_COLUMNS.map(([key, label]) => (
              <th key={key} data-col={key} className={scannerColClass(key)}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
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
