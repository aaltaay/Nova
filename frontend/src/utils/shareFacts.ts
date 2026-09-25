/**
 * Float and short-interest text for the scanner, the quote panel and the Trader side column (#532):
 * a contradicted float reads "54.0K?" with its reason, short interest carries its FINRA settlement
 * date, and short interest above the float reads "9.0M!" in amber -- a warning, never a gate.
 * Pure; strings live in constantGroups/share_facts.ts.
 */
import {
  FLOAT_CONTRADICTED_FALLBACK,
  FLOAT_CONTRADICTED_MARK,
  SHORT_ABOVE_FLOAT_CLASS,
  SHORT_ABOVE_FLOAT_FALLBACK,
  SHORT_ABOVE_FLOAT_MARK,
  SHORT_INTEREST_NO_DATE,
  SHORT_INTEREST_SOURCE,
  shortRatioTitle,
} from '../constantGroups/share_facts';
import { fmtVolume } from './quoteFormat';

function epochDate(ts: number | null | undefined): Date | null {
  return typeof ts === 'number' && Number.isFinite(ts) ? new Date(ts * 1000) : null;
}

/** "Aug 31": FINRA's settlement date, which Yahoo stamps at midnight UTC. Null when unknown. */
export function fmtSettlementDate(ts: number | null | undefined): string | null {
  const d = epochDate(ts);
  return d ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }) : null;
}

/** "8/31": the same date for the scanner's narrow Short cell. */
export function fmtSettlementDateShort(ts: number | null | undefined): string | null {
  const d = epochDate(ts);
  return d ? `${d.getUTCMonth() + 1}/${d.getUTCDate()}` : null;
}

function fmtSettlementDateLong(ts: number | null | undefined): string | null {
  const d = epochDate(ts);
  return d
    ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
    : null;
}

/** "54.0K?" when Yahoo's own share counts contradict the float, else the float as it always read. */
export function fmtFloat(float: number | null | undefined, contradicted: boolean | null | undefined): string {
  const text = fmtVolume(float);
  return contradicted === true && float != null && Number.isFinite(float) ? `${text}${FLOAT_CONTRADICTED_MARK}` : text;
}

/** The short-above-float warning's words when the backend raised it; undefined otherwise. */
export function shortAboveFloatWarning(
  above: boolean | null | undefined,
  reason?: string | null,
): string | undefined {
  return above === true ? reason || SHORT_ABOVE_FLOAT_FALLBACK : undefined;
}

/** The amber class for short interest above the float; undefined otherwise. */
export function shortAboveFloatClass(above: boolean | null | undefined): string | undefined {
  return above === true ? SHORT_ABOVE_FLOAT_CLASS : undefined;
}

/**
 * Why a flagged float is doubtful, and the short-above-float warning when there is one; undefined
 * for any other float (no tooltip).
 */
export function floatTitle(
  contradicted: boolean | null | undefined,
  reason: string | null | undefined,
  shortWarning?: string,
): string | undefined {
  const parts = [contradicted === true ? reason || FLOAT_CONTRADICTED_FALLBACK : undefined, shortWarning];
  const text = parts.filter(Boolean).join('. ');
  return text || undefined;
}

/**
 * "566.0K (Aug 31)": short interest with its settlement date when Yahoo gave one; "9.0M! (Aug 31)"
 * when it is above the float (a warning, never a gate).
 */
export function fmtShortInterest(
  si: number | null | undefined,
  ts: number | null | undefined,
  above?: boolean | null,
): string {
  if (si == null || !Number.isFinite(si)) return fmtVolume(si);
  const text = `${fmtVolume(si)}${above === true ? SHORT_ABOVE_FLOAT_MARK : ''}`;
  const date = fmtSettlementDate(ts);
  return date ? `${text} (${date})` : text;
}

/**
 * The hover for a short-interest figure: the short-above-float warning first when there is one, then
 * its settlement date and source, and the ratio named as Yahoo's.
 */
export function shortInterestTitle(
  si: number | null | undefined,
  ts: number | null | undefined,
  ratio?: number | null,
  shortWarning?: string,
): string | undefined {
  const parts: string[] = [];
  if (shortWarning && si != null && Number.isFinite(si)) parts.push(`${shortWarning}.`);
  if (si != null && Number.isFinite(si)) {
    const date = fmtSettlementDateLong(ts);
    parts.push(
      `Short interest ${fmtVolume(si)}, ${date ? `FINRA settlement ${date}` : SHORT_INTEREST_NO_DATE} -- ${SHORT_INTEREST_SOURCE}.`,
    );
  }
  if (ratio != null && Number.isFinite(ratio)) parts.push(shortRatioTitle(ratio.toFixed(1)));
  return parts.length ? parts.join(' ') : undefined;
}
