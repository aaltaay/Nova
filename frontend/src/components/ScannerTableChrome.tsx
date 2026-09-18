/** Shared # column for scanner-style tables (not HOD / Running Up). */
import { SCANNER_ROW_NUM_LABEL, SCANNER_ROW_NUM_TITLE } from '../constants';
import { scannerColClass } from './scannerTableCol';

export function ScannerColGroup({ columns }: { columns: [string, string][] }) {
  return (
    <colgroup>
      <col className="scanner-col scanner-col--rownum" />
      {columns.map(([key]) => (
        <col key={key} className={scannerColClass(key)} />
      ))}
    </colgroup>
  );
}

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
