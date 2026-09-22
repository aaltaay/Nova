/** Small scanner-row cells and formatters (split from ScannerTableRow.tsx). */
import { fmtPct } from '../utils/quoteFormat';
import {
  SCANNER_CELL_ABSENT,
  SCANNER_GAP_BAR_MAX_PX,
  SCANNER_RVOL_SOURCE_MARKS,
  SCANNER_RVOL_SOURCE_UNREPORTED,
  type ScannerRvolSourceMark,
} from '../constantGroups/scanner_board';

/** The RVOL mark for a row: the source it names, or a stated "not reported" (QA C39). */
export function rvolSourceMark(source: string | null | undefined): ScannerRvolSourceMark {
  return (source && SCANNER_RVOL_SOURCE_MARKS[source]) || SCANNER_RVOL_SOURCE_UNREPORTED;
}

/** Signed gap plus a bar scaled to the list's top row (drawn, not just printed). */
export function GapCell({ value, scaleMax }: { value: number | null; scaleMax: number | null }) {
  if (value == null) return <span className="na-muted">{SCANNER_CELL_ABSENT}</span>;
  const cls = value >= 0 ? 'positive' : 'negative';
  const width = scaleMax != null && scaleMax > 0
    ? Math.round(Math.min(1, Math.abs(value) / scaleMax) * SCANNER_GAP_BAR_MAX_PX)
    : null;
  return (
    <span className="scanner-gap">
      <span className={cls}>{fmtPct(value)}</span>
      {width != null ? (
        <span className="scanner-gap__bar" aria-hidden="true">
          <i className={value >= 0 ? 'is-up' : 'is-down'} style={{ width }} />
        </span>
      ) : null}
    </span>
  );
}

export function fmtChangeAbs(v: number | null | undefined): string {
  if (v == null) return '—';
  return `${v >= 0 ? '+' : '-'}$${Math.abs(v).toFixed(2)}`;
}

export function pctClass(v: number | null | undefined): string {
  if (v == null) return '';
  return v >= 0 ? 'positive' : 'negative';
}
