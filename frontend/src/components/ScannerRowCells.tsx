/** Small scanner-row cells and formatters (split from ScannerTableRow.tsx). */
import { fmtPct, fmtVolume, pctToneClass, roundsToZero } from '../utils/quoteFormat';
import {
  SCANNER_CELL_ABSENT,
  SCANNER_GAP_BAR_MAX_PX,
  SCANNER_RVOL_SOURCE_MARKS,
  SCANNER_RVOL_SOURCE_UNREPORTED,
  type ScannerRvolSourceMark,
} from '../constantGroups/scanner_board';
import { SHORT_RATIO_CELL_SUFFIX } from '../constantGroups/share_facts';
import { fmtFloat, fmtSettlementDateShort, floatTitle, shortInterestTitle } from '../utils/shareFacts';
import type { ScannerRow } from '../types/scanner';

/** Yahoo's float; "54.0K?" with the reason on hover when Yahoo's own counts contradict it (#532). */
export function FloatCell({ row }: { row: ScannerRow }) {
  if (row.float == null) return <span className="na-muted">{SCANNER_CELL_ABSENT}</span>;
  const flagged = row.float_contradicted === true;
  return (
    <span title={floatTitle(row.float_contradicted, row.float_contradicted_reason)}
      data-float-contradicted={flagged ? 'true' : undefined}>
      {fmtFloat(row.float, row.float_contradicted)}
    </span>
  );
}

/** Short interest over its FINRA settlement date and Yahoo's ratio ("8/31 · 6.9"); the hover names both (#532). */
export function ShortInterestCell({ row }: { row: ScannerRow }) {
  const date = row.short_interest != null ? fmtSettlementDateShort(row.short_interest_ts) : null;
  const ratio = row.short_ratio != null ? row.short_ratio.toFixed(1) : null;
  const second = date && ratio ? `${date} · ${ratio}` : date ?? (ratio ? `${ratio}${SHORT_RATIO_CELL_SUFFIX}` : null);
  return (
    <span className="cell-stack" title={shortInterestTitle(row.short_interest, row.short_interest_ts, row.short_ratio)}>
      <span className="cell-stack-primary">
        {row.short_interest != null ? fmtVolume(row.short_interest) : <span className="na-muted">{SCANNER_CELL_ABSENT}</span>}
      </span>
      <span className="cell-stack-secondary">
        {second ?? <span className="na-muted">{SCANNER_CELL_ABSENT}</span>}
      </span>
    </span>
  );
}

/** The RVOL mark for a row: the source it names, or a stated "not reported" (QA C39). */
export function rvolSourceMark(source: string | null | undefined): ScannerRvolSourceMark {
  return (source && SCANNER_RVOL_SOURCE_MARKS[source]) || SCANNER_RVOL_SOURCE_UNREPORTED;
}

/** Signed gap plus a bar scaled to the list's top row (drawn, not just printed). */
export function GapCell({ value, scaleMax }: { value: number | null; scaleMax: number | null }) {
  if (value == null) return <span className="na-muted">{SCANNER_CELL_ABSENT}</span>;
  const cls = pctToneClass(value);
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
  if (v == null || !Number.isFinite(v)) return '—';
  // A change that prints as $0.00 is flat: no sign (QA W21).
  if (roundsToZero(v, 2)) return '$0.00';
  return `${v > 0 ? '+' : '-'}$${Math.abs(v).toFixed(2)}`;
}

/** positive / negative, none when the figure prints as flat (QA W21). */
export function pctClass(v: number | null | undefined): string {
  return pctToneClass(v);
}
