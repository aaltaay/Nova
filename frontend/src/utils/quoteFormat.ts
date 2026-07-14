/** Quote-card formatters shared by ticker detail UI. */
import { ALPACA_ASSET_ATTRIBUTE_LABELS } from '../constants';

export function fmtVolume(v: number | null | undefined): string {
  if (v == null) return '—';
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(v);
}

export function fmtMarketCap(v: number | null | undefined): string {
  if (v == null) return '—';
  if (v >= 1_000_000_000_000) return `$${(v / 1_000_000_000_000).toFixed(2)}T`;
  if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v}`;
}

export function fmtPct(frac: number | null, fallback = 'N/A'): string {
  if (frac == null) return fallback;
  return `${frac > 0 ? '+' : ''}${(frac * 100).toFixed(2)}%`;
}

export function fmtPrice(p: number | null | undefined): string {
  if (p == null) return '—';
  return `$${p.toFixed(2)}`;
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
