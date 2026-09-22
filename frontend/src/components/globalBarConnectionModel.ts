/**
 * The one connection chip on the global bar (redesign, 2026-09-22): a single
 * quiet word about the desk, with the old status cluster's facts folded into
 * its tooltip. Pure -- the component gathers the inputs.
 *
 * Priority (first match wins): SAMPLE DATA · API down · STALE (status poll) ·
 * IBKR offline · STALE <age> (late scanner prices) · IBKR delayed · IBKR live.
 */
import {
  DATA_FEED_LABELS,
  GLOBAL_BAR_CONNECTION_API_DOWN_LABEL,
  GLOBAL_BAR_CONNECTION_CLICK_HINT,
  GLOBAL_BAR_CONNECTION_DELAYED_LABEL,
  GLOBAL_BAR_CONNECTION_LIVE_LABEL,
  GLOBAL_BAR_CONNECTION_PRICES_PREFIX,
  GLOBAL_BAR_CONNECTION_SAMPLE_LABEL,
  GLOBAL_BAR_CONNECTION_SAMPLE_TITLE,
  GLOBAL_BAR_CONNECTION_SCANNER_MODE_PREFIX,
  GLOBAL_BAR_CONNECTION_STALE_LABEL,
  GLOBAL_BAR_FEED_FALLBACK_TITLE,
  GLOBAL_BAR_OFFLINE_CHIP,
  globalBarLegacyFeedTitle,
} from '../constants';
import {
  SCANNER_HONESTY_CHIP_ROLE,
  priceAgeChipText,
  showPriceAgeChip,
} from '../scanner/scannerHonesty';
import { formatScanAge } from '../utils/formatScanAge';

export type ConnectionChipTone = 'ok' | 'warn' | 'bad';
export type ConnectionChipState =
  | 'sample'
  | 'api-down'
  | 'stale'
  | 'offline'
  | 'delayed'
  | 'live';

export interface ConnectionChipInput {
  sampleDataActive: boolean;
  apiOk: boolean;
  /** API half of the tooltip (reachable / flag hint). */
  apiTitle: string;
  connected: boolean;
  /** /api/ibkr/status poll has gone stale (last-good answer is old). */
  statusStale: boolean;
  /** Seconds since the status poll went stale; null when unknown. */
  staleForSec: number | null;
  delayed: boolean;
  /** Gateway half of the tooltip (headerConnectionStatusModel.deskGatewayView). */
  gatewayTitle: string;
  pricesStale: boolean;
  secondsAgo: number | null;
  lastPriceTs?: number | null;
  historyDate: string | null;
  honestyText?: string | null;
  isIbkr: boolean;
  activeFeed: string;
  feedFellBack: boolean;
  /** Backend scanner mode ("Market Closed") -- tooltip only. */
  scannerModeLabel?: string | null;
}

export interface ConnectionChipView {
  tone: ConnectionChipTone;
  state: ConnectionChipState;
  label: string;
  title: string;
}

/** "42s" / "3m" / "5h" / "2d" -- the chip has room for one number. */
export function compactAge(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

function feedLine(i: ConnectionChipInput): string | null {
  if (i.isIbkr) return null;
  if (i.feedFellBack) return GLOBAL_BAR_FEED_FALLBACK_TITLE;
  return globalBarLegacyFeedTitle(DATA_FEED_LABELS[i.activeFeed] || i.activeFeed.toUpperCase());
}

export function connectionChipView(i: ConnectionChipInput): ConnectionChipView {
  const showPrices = showPriceAgeChip({
    historyDate: i.historyDate,
    lastPriceTs: i.lastPriceTs,
    secondsAgo: i.secondsAgo,
  });
  const priceText = showPrices
    ? priceAgeChipText({
        lastPriceTs: i.lastPriceTs,
        secondsAgo: i.secondsAgo,
        pricesStale: i.pricesStale,
        formatAge: formatScanAge,
      })
    : null;
  const pricesLate = showPrices && i.pricesStale && i.secondsAgo != null;

  let tone: ConnectionChipTone;
  let state: ConnectionChipState;
  let label: string;
  if (i.sampleDataActive) {
    [tone, state, label] = ['warn', 'sample', GLOBAL_BAR_CONNECTION_SAMPLE_LABEL];
  } else if (!i.apiOk) {
    [tone, state, label] = ['bad', 'api-down', GLOBAL_BAR_CONNECTION_API_DOWN_LABEL];
  } else if (i.statusStale) {
    const age = i.staleForSec != null ? ` ${compactAge(i.staleForSec)}` : '';
    [tone, state, label] = ['warn', 'stale', `${GLOBAL_BAR_CONNECTION_STALE_LABEL}${age}`];
  } else if (!i.connected) {
    [tone, state, label] = ['bad', 'offline', GLOBAL_BAR_OFFLINE_CHIP];
  } else if (pricesLate) {
    const age = compactAge(i.secondsAgo as number);
    [tone, state, label] = ['warn', 'stale', `${GLOBAL_BAR_CONNECTION_STALE_LABEL} ${age}`];
  } else if (i.delayed) {
    [tone, state, label] = ['warn', 'delayed', GLOBAL_BAR_CONNECTION_DELAYED_LABEL];
  } else {
    [tone, state, label] = ['ok', 'live', GLOBAL_BAR_CONNECTION_LIVE_LABEL];
  }

  const lines: (string | null)[] = [label];
  if (i.sampleDataActive) {
    lines.push(GLOBAL_BAR_CONNECTION_SAMPLE_TITLE);
  } else {
    lines.push(i.apiTitle, i.gatewayTitle);
  }
  lines.push(priceText ? `${GLOBAL_BAR_CONNECTION_PRICES_PREFIX} ${priceText}` : null);
  lines.push(i.honestyText ? `${SCANNER_HONESTY_CHIP_ROLE}: ${i.honestyText}` : null);
  lines.push(feedLine(i));
  lines.push(
    i.scannerModeLabel ? `${GLOBAL_BAR_CONNECTION_SCANNER_MODE_PREFIX} ${i.scannerModeLabel}` : null,
  );
  lines.push(GLOBAL_BAR_CONNECTION_CLICK_HINT);
  return { tone, state, label, title: lines.filter(Boolean).join('\n\n') };
}
