/** Quote-card formatters shared by ticker detail UI. */
import { ALPACA_ASSET_ATTRIBUTE_LABELS } from '../constants';

type Unit = readonly [divisor: number, suffix: string, digits: number];

/** Share counts (volume, float, short interest): K / M / B. */
const COUNT_UNITS: readonly Unit[] = [[1e3, 'K', 1], [1e6, 'M', 1], [1e9, 'B', 2]];
/** Market cap: K / M / B / T. */
const CAP_UNITS: readonly Unit[] = [[1e3, 'K', 1], [1e6, 'M', 1], [1e9, 'B', 2], [1e12, 'T', 2]];

/**
 * The value in the largest unit it reaches, promoted when rounding reaches
 * 1000 of the unit: 999,960 is "1.0M", never "1000.0K"; 1.23B is "1.23B",
 * never "1234.6M" (QA W22, 2026-09-22). Null below the smallest unit.
 */
function scaled(v: number, units: readonly Unit[]): string | null {
  const abs = Math.abs(v);
  let i = -1;
  for (let k = 0; k < units.length; k += 1) if (abs >= units[k][0]) i = k;
  if (i < 0 && abs >= units[0][0] * 0.9995) i = 0;
  if (i < 0) return null;
  let text = (abs / units[i][0]).toFixed(units[i][2]);
  if (Number(text) >= 1000 && i + 1 < units.length) {
    i += 1;
    text = (abs / units[i][0]).toFixed(units[i][2]);
  }
  return `${v < 0 ? '-' : ''}${text}${units[i][1]}`;
}

export function fmtVolume(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return scaled(v, COUNT_UNITS) ?? String(Math.round(v));
}

export function fmtMarketCap(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const text = scaled(v, CAP_UNITS);
  return text ? `$${text}` : `$${Math.round(v)}`;
}

/** True when the figure prints as zero at `digits` places: it has no sign and no tone. */
export function roundsToZero(value: number, digits: number): boolean {
  return Number(Math.abs(value).toFixed(digits)) === 0;
}

/**
 * A fraction as a signed percent. A move that prints as 0.00% is flat: no
 * sign, never "-0.00%" / "+0.00%" (QA W21).
 */
export function fmtPct(frac: number | null, fallback = 'N/A'): string {
  if (frac == null || !Number.isFinite(frac)) return fallback;
  const pct = frac * 100;
  if (roundsToZero(pct, 2)) return '0.00%';
  const sign = pct > 0 ? '+' : '';
  // Four digits and up drop the decimals and group the thousands, so the
  // figure fits its column: "+12,500%", never "+12499.93%.." (QA D15).
  if (Math.abs(pct) >= 1000) return `${sign}${Math.round(pct).toLocaleString('en-US')}%`;
  return `${sign}${pct.toFixed(2)}%`;
}

/** positive / negative for a fraction, none when it prints as flat. */
export function pctToneClass(frac: number | null | undefined): '' | 'positive' | 'negative' {
  if (frac == null || !Number.isFinite(frac) || roundsToZero(frac * 100, 2)) return '';
  return frac > 0 ? 'positive' : 'negative';
}

/**
 * A price with thousands separators; a sub-dollar price keeps its sub-penny
 * digits (up to four) -- 0.678 is "$0.678", not "$0.68" (QA W23, D15).
 */
export function fmtPrice(p: number | null | undefined): string {
  if (p == null || !Number.isFinite(p)) return '—';
  const abs = Math.abs(p);
  const body = abs.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: abs > 0 && abs < 1 ? 4 : 2,
  });
  return `${p < 0 ? '-' : ''}$${body}`;
}

/** A relative volume; a real ratio under 0.01 reads "<0.01x", never "0x" (QA W22). */
export function fmtRvol(v: number | null | undefined, suffix = 'x'): string | null {
  if (v == null || !Number.isFinite(v)) return null;
  if (v < 0.01) return `<0.01${suffix}`;
  return `${Number(v.toFixed(2))}${suffix}`;
}

/**
 * Session open / high / low. Treat null, 0, and negative as missing —
 * IBKR discovery often omits OHLC, and a literal 0 must not render as "$0.00".
 */
export function sessionPriceOrNull(p: number | null | undefined): number | null {
  if (p == null || !(p > 0)) return null;
  return p;
}

export function fmtSessionPrice(p: number | null | undefined): string {
  return fmtPrice(sessionPriceOrNull(p));
}

export function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function fmtTimestamp(iso: string | null | undefined): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      timeZoneName: 'short',
    });
  } catch {
    return iso;
  }
}

export function fmtYesNo(v: boolean | undefined): string {
  if (v === true) return 'Yes';
  if (v === false) return 'No';
  return '—';
}

export function fmtMaintMarginPct(v: number | null | undefined): string {
  if (v == null) return '—';
  return `${Number(v)}%`;
}

export function fmtMarginReqString(v: string | null | undefined): string {
  if (v == null || v === '') return '—';
  const s = String(v).trim();
  return s.endsWith('%') ? s : `${s}%`;
}

export function formatAssetAttributeList(attrs: string[] | undefined): string {
  if (!attrs?.length) return '—';
  return attrs
    .map(a => ALPACA_ASSET_ATTRIBUTE_LABELS[a] ?? a.replace(/_/g, ' '))
    .join(', ');
}
