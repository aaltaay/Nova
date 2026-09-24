/**
 * Float and short-interest text for the scanner, the quote panel and the Trader side column (#532):
 * a contradicted float reads "54.0K?" with its reason, and short interest carries its FINRA
 * settlement date. Pure; strings live in constantGroups/share_facts.ts.
 */
import {
  FLOAT_CONTRADICTED_FALLBACK,
  FLOAT_CONTRADICTED_MARK,
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

/** Why a flagged float is doubtful; undefined for any other float (no tooltip). */
export function floatTitle(
  contradicted: boolean | null | undefined,
  reason: string | null | undefined,
): string | undefined {
  if (contradicted !== true) return undefined;
  return reason || FLOAT_CONTRADICTED_FALLBACK;
}

/** "566.0K (Aug 31)": short interest with its settlement date when Yahoo gave one. */
export function fmtShortInterest(si: number | null | undefined, ts: number | null | undefined): string {
  const text = fmtVolume(si);
  const date = fmtSettlementDate(ts);
  return si != null && Number.isFinite(si) && date ? `${text} (${date})` : text;
}

/** The hover for a short-interest figure: its settlement date and source, and the ratio named as Yahoo's. */
export function shortInterestTitle(
  si: number | null | undefined,
  ts: number | null | undefined,
  ratio?: number | null,
): string | undefined {
  const parts: string[] = [];
  if (si != null && Number.isFinite(si)) {
    const date = fmtSettlementDateLong(ts);
    parts.push(
      `Short interest ${fmtVolume(si)}, ${date ? `FINRA settlement ${date}` : SHORT_INTEREST_NO_DATE} -- ${SHORT_INTEREST_SOURCE}.`,
    );
  }
  if (ratio != null && Number.isFinite(ratio)) parts.push(shortRatioTitle(ratio.toFixed(1)));
  return parts.length ? parts.join(' ') : undefined;
}
