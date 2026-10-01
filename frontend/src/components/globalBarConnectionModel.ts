/**
 * The one connection chip on the global bar (redesign, 2026-09-22): a single
 * quiet word about the desk, with the old status cluster's facts folded into
 * its tooltip. Pure -- the component gathers the inputs.
 *
 * Priority (first match wins): SAMPLE DATA · API down · STALE (status poll) ·
 * IBKR offline · NO DATA <age> / DATA GAP <length> (the IBKR feed went silent,
 * #672) · STALE <age> (late scanner prices) · IBKR delayed · IBKR live.
 *
 * STALE <age> means the newest scanner price is older than SCANNER_PRICE_STALE_SEC.
 * An L1 subscription error with fresh prices is not stale: it read "STALE 0S" all
 * morning on 2026-10-01 (Error 101, max tickers), so a real silence looked the same;
 * the error stays in the tooltip's scanner line.
 *
 * On Sim `connected` is the Gateway socket (the backend forces the session
 * `connected` there because the replay needs no Gateway), and an offline
 * Gateway is amber, not red -- only the live edge needs it (C24).
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
  GLOBAL_BAR_CONNECTION_CHECKING_LABEL,
  GLOBAL_BAR_CONNECTION_CHECKING_TITLE,
  GLOBAL_BAR_CONNECTION_SIM_OFFLINE_TITLE,
  rosterScannerError,
} from '../constantGroups/global_bar';
import { SCANNER_PRICE_STALE_SEC } from '../constantGroups/chart_api';
import type { FeedGapBadge } from '../ibkr/feedPulse';
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
  | 'checking'
  | 'stale'
  | 'offline'
  | 'no-data'
  | 'data-gap'
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
  /**
   * The first status poll has not answered: nothing is known about IB
   * Gateway yet, so the chip says it is checking -- "IBKR offline" before any
   * answer blamed the Gateway for a request still in flight (QA D10).
   */
  statusPending?: boolean;
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
  /** ADR 020 desk venue; on Sim `connected` must be the Gateway socket (C24). */
  venue?: 'live' | 'paper' | 'sim' | null;
  /** The IBKR feed is silent now, or was a moment ago (`ibkr/feedPulse.ts`, #672). */
  feedGap?: FeedGapBadge | null;
}

const RAW_SCANNER_ERROR = /^\s*(ibkr|alpaca)\s*:\s*([A-Za-z]*(?:Error|Exception))\b/i;

/**
 * The Roster line in words, not a Python repr (V34): "ibkr: TimeoutError:
 * TimeoutError()" reads "IBKR scanner request timed out". Text that is not a
 * raw exception passes through unchanged.
 */
export function humanRosterText(text: string | null | undefined): string | null {
  if (!text) return null;
  const raw = RAW_SCANNER_ERROR.exec(text);
  return raw ? rosterScannerError(raw[1].toUpperCase(), raw[2]) : text;
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
  const late = i.pricesStale && i.secondsAgo != null && i.secondsAgo > SCANNER_PRICE_STALE_SEC;
  const priceText = showPrices
    ? priceAgeChipText({
        lastPriceTs: i.lastPriceTs,
        secondsAgo: i.secondsAgo,
        pricesStale: late,
        formatAge: formatScanAge,
      })
    : null;
  const pricesLate = showPrices && late;

  let tone: ConnectionChipTone;
  let state: ConnectionChipState;
  let label: string;
  if (i.sampleDataActive) {
    [tone, state, label] = ['warn', 'sample', GLOBAL_BAR_CONNECTION_SAMPLE_LABEL];
  } else if (!i.apiOk) {
    [tone, state, label] = ['bad', 'api-down', GLOBAL_BAR_CONNECTION_API_DOWN_LABEL];
  } else if (i.statusPending && !i.connected) {
    [tone, state, label] = ['warn', 'checking', GLOBAL_BAR_CONNECTION_CHECKING_LABEL];
  } else if (i.statusStale) {
    const age = i.staleForSec != null ? ` ${compactAge(i.staleForSec)}` : '';
    [tone, state, label] = ['warn', 'stale', `${GLOBAL_BAR_CONNECTION_STALE_LABEL}${age}`];
  } else if (!i.connected) {
    [tone, state, label] = [i.venue === 'sim' ? 'warn' : 'bad', 'offline', GLOBAL_BAR_OFFLINE_CHIP];
  } else if (i.feedGap) {
    [tone, state, label] = [i.feedGap.tone, i.feedGap.state, i.feedGap.label];
  } else if (pricesLate) {
    const age = compactAge(i.secondsAgo as number);
    [tone, state, label] = ['warn', 'stale', `${GLOBAL_BAR_CONNECTION_STALE_LABEL} ${age}`];
  } else if (i.delayed) {
    [tone, state, label] = ['warn', 'delayed', GLOBAL_BAR_CONNECTION_DELAYED_LABEL];
  } else {
    [tone, state, label] = ['ok', 'live', GLOBAL_BAR_CONNECTION_LIVE_LABEL];
  }

  const lines: (string | null)[] = [label];
  if (state === 'no-data' || state === 'data-gap') lines.push(i.feedGap?.title ?? null);
  if (i.sampleDataActive) {
    lines.push(GLOBAL_BAR_CONNECTION_SAMPLE_TITLE);
  } else {
    lines.push(i.apiTitle, state === 'checking' ? GLOBAL_BAR_CONNECTION_CHECKING_TITLE : i.gatewayTitle);
    if (state === 'offline' && i.venue === 'sim') lines.push(GLOBAL_BAR_CONNECTION_SIM_OFFLINE_TITLE);
  }
  lines.push(priceText ? `${GLOBAL_BAR_CONNECTION_PRICES_PREFIX} ${priceText}` : null);
  const roster = humanRosterText(i.honestyText);
  lines.push(roster ? `${SCANNER_HONESTY_CHIP_ROLE}: ${roster}` : null);
  lines.push(feedLine(i));
  lines.push(
    i.scannerModeLabel ? `${GLOBAL_BAR_CONNECTION_SCANNER_MODE_PREFIX} ${i.scannerModeLabel}` : null,
  );
  lines.push(GLOBAL_BAR_CONNECTION_CLICK_HINT);
  return { tone, state, label, title: lines.filter(Boolean).join('\n\n') };
}
