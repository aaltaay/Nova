import { ScannerRowNumCell, ScannerRowNumHeader } from '../components/ScannerTable';
import { SelectableTableRow } from '../components/SelectableTableRow';
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
    <div className="table-wrapper">
      <table data-testid="volume-boost-table">
        <thead>
          <tr>
            <ScannerRowNumHeader />
            {VOLUME_BOOST_COLUMNS.map(([key, label]) => (
              <th key={key}>{label}</th>
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
              <td>
                <SymbolSelectButton
                  symbol={row.symbol}
                  selected={selectedSymbol === row.symbol}
                  onSelect={onSelect}
                  onOpenTrading={onOpenTrading}
                />
              </td>
              <td>{fmtPrice(row.price)}</td>
              <td className="volume-boost-ratio">
                {row.spike_ratio != null ? `${row.spike_ratio.toFixed(1)}x` : '--'}
              </td>
              <td>{fmtVolume(row.spike_shares)}</td>
              <td>{formatSpikeAge(row.age_sec)}</td>
              <td>
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
