/**
 * Paper | Live | Sim venue capsule (ADR 020 -- three venues on one feed).
 * Every pill POSTs /api/desk/venue {venue}. Paper is Nova's practice account
 * on the live feed and never launches a Gateway. Live also keeps ensuring the
 * live Gateway through POST /api/ibkr/gateway-mode. Sim falls back to the
 * legacy POST /api/sim when the venue route is missing (stale API process).
 * Never sets IBKR_LIVE_TRADING_CONFIRMED -- live spend stays a separate gate.
 * Session Record is per-tab (right-click), not a capsule mode.
 */
import { useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import {
  API_BASE_URL,
  APP_DIALOG_SWITCH_LABEL,
  DESK_VENUE_API_PATH,
  DESK_VENUE_API_RESTART_HINT,
  DESK_VENUE_CONFIRM_LIVE_TITLE,
  DESK_VENUE_CONFIRM_PAPER_TITLE,
  DESK_VENUE_CONFIRM_SIM_TITLE,
  DESK_VENUE_GATEWAY_MODE_API_PATH,
  DESK_VENUE_LIVE_TITLE,
  DESK_VENUE_PAPER_TITLE,
  DESK_VENUE_SIM_FALLBACK_API_PATH,
  DESK_VENUE_SIM_TITLE,
  DESK_VENUE_SWITCH_UNREACHABLE,
  deskVenueSwitchFailed,
  deskVenueSwitchingWhy,
  GATEWAY_MODE_API_RESTART_HINT,
  GLOBAL_BAR_MODE_LIVE,
  GLOBAL_BAR_MODE_PAPER,
  GLOBAL_BAR_MODE_SIM,
} from '../constants';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { SAMPLE_VENUE_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { confirmApp } from '../ux';
import { explicitVenueOf } from './deskVenue';
import { disconnectHintSwitchTarget } from './disconnectCopy';
import type { IbkrMode } from './types';
import { refreshIbkrStatusNow, useIbkrStatus } from './useIbkrStatus';

interface VenueResponse {
  ok?: boolean;
  error?: string | null;
  detail?: string;
  venue?: DeskVenue;
  mode?: IbkrMode;
  launch_action?: string | null;
  message?: string | null;
  sim?: boolean;
}

export type CapsuleSelection = DeskVenue;

export interface GatewayModeCapsuleProps {
  mode: IbkrMode;
  /** ADR 020 -- explicit venue from /api/ibkr/status; wins over the older fields. */
  venue?: DeskVenue | null;
  gatewayMode?: 'paper' | 'live';
  accountKind?: string | null;
  intentionalMode?: 'paper' | 'live' | null;
  disconnectHint?: string | null;
  testId?: string;
  errorTestId?: string;
  className?: string;
}

const VENUE_TITLE: Record<DeskVenue, string> = {
  paper: DESK_VENUE_PAPER_TITLE,
  live: DESK_VENUE_LIVE_TITLE,
  sim: DESK_VENUE_SIM_TITLE,
};
const VENUE_CONFIRM_TITLE: Record<DeskVenue, string> = {
  paper: DESK_VENUE_CONFIRM_PAPER_TITLE,
  live: DESK_VENUE_CONFIRM_LIVE_TITLE,
  sim: DESK_VENUE_CONFIRM_SIM_TITLE,
};
const VENUE_LABEL: Record<DeskVenue, string> = {
  paper: GLOBAL_BAR_MODE_PAPER,
  live: GLOBAL_BAR_MODE_LIVE,
  sim: GLOBAL_BAR_MODE_SIM,
};
const VENUE_ORDER: DeskVenue[] = ['paper', 'live', 'sim'];

function isRouteMissing(res: Response, body: VenueResponse): boolean {
  if (res.status === 404) return true;
  const detail = typeof body.detail === 'string' ? body.detail : '';
  return Boolean(detail) && detail.toLowerCase().includes('not found');
}

function switchErrorMessage(
  res: Response,
  body: VenueResponse,
  next: DeskVenue,
  restartHint: string,
): string {
  if (isRouteMissing(res, body)) return restartHint;
  const detail = typeof body.detail === 'string' ? body.detail : '';
  return body.error || detail || deskVenueSwitchFailed(next);
}

async function postJson(path: string, payload: unknown): Promise<[Response, VenueResponse]> {
  const res = await novaFetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const body: VenueResponse = await res.json().catch(() => ({}));
  return [res, body];
}

export function resolveCapsuleSelection(
  mode: IbkrMode,
  gatewayMode?: 'paper' | 'live',
  accountKind?: string | null,
  intentional?: 'paper' | 'live' | null,
  venue?: DeskVenue | null,
): CapsuleSelection | null {
  if (venue === 'paper' || venue === 'live' || venue === 'sim') return venue;
  if (mode === 'sim') return 'sim';
  if (intentional === 'paper' || intentional === 'live') return intentional;
  if (mode === 'live' || mode === 'paper') return mode;
  if (accountKind === 'paper' || accountKind === 'live') return accountKind;
  if (gatewayMode === 'live' || gatewayMode === 'paper') return gatewayMode;
  return null;
}

export function GatewayModeCapsule({
  mode,
  venue = null,
  gatewayMode,
  accountKind = null,
  intentionalMode = null,
  disconnectHint,
  testId = 'gateway-mode-capsule',
  errorTestId,
  className,
}: GatewayModeCapsuleProps) {
  const [pending, setPending] = useState<CapsuleSelection | null>(null);
  // ADR 020: the status `venue` is the one truth; `mode` is the Gateway port
  // label on Live, so the by-hand paper Gateway must not read as Paper (C26).
  const statusVenue = explicitVenueOf(useIbkrStatus());
  const selected =
    pending
    ?? resolveCapsuleSelection(mode, gatewayMode, accountKind, intentionalMode, venue ?? statusVenue);
  const [switching, setSwitching] = useState<CapsuleSelection | null>(null);
  const [switchError, setSwitchError] = useState<string | null>(null);
  const hintTarget = disconnectHintSwitchTarget(disconnectHint);
  // Every pill locks while one switch runs, and says so (ux/whyTip.ts).
  const switchingWhy = switching ? deskVenueSwitchingWhy(VENUE_LABEL[switching]) : undefined;

  /** Legacy Sim toggle for an API process that predates /api/desk/venue. */
  async function legacySimFallback(): Promise<string | null> {
    const [res, body] = await postJson(DESK_VENUE_SIM_FALLBACK_API_PATH, { enabled: true });
    if (!res.ok || body.sim !== true) {
      return switchErrorMessage(res, body, 'sim', DESK_VENUE_API_RESTART_HINT);
    }
    return null;
  }

  /** Live keeps ensuring the live Gateway; its message names IBC's launch action. */
  async function ensureLiveGateway(): Promise<string | null> {
    const [res, body] = await postJson(DESK_VENUE_GATEWAY_MODE_API_PATH, { mode: 'live' });
    if (!res.ok || !body.ok) {
      return switchErrorMessage(res, body, 'live', GATEWAY_MODE_API_RESTART_HINT);
    }
    if (body.message && body.launch_action && body.launch_action !== 'noop') {
      return body.message;
    }
    return null;
  }

  async function switchVenue(next: DeskVenue): Promise<string | null> {
    const [res, body] = await postJson(DESK_VENUE_API_PATH, { venue: next });
    if (isRouteMissing(res, body)) {
      if (next === 'sim') return legacySimFallback();
      return DESK_VENUE_API_RESTART_HINT;
    }
    if (!res.ok || body.venue !== next) {
      return switchErrorMessage(res, body, next, DESK_VENUE_API_RESTART_HINT);
    }
    return next === 'live' ? ensureLiveGateway() : null;
  }

  async function requestVenue(next: DeskVenue) {
    if (next === selected || switching) return;
    // V4: the venue is the live desk's; the sample desk switches nothing.
    if (onSampleDesk()) {
      setSwitchError(SAMPLE_VENUE_REFUSAL);
      return;
    }
    const confirmed = await confirmApp({
      title: VENUE_CONFIRM_TITLE[next],
      message: VENUE_TITLE[next],
      confirmLabel: APP_DIALOG_SWITCH_LABEL,
      tone: next === 'live' ? 'danger' : 'warning',
    });
    if (!confirmed) return;

    setPending(next);
    setSwitching(next);
    setSwitchError(null);
    try {
      setSwitchError(await switchVenue(next));
    } catch {
      setSwitchError(DESK_VENUE_SWITCH_UNREACHABLE);
    } finally {
      setSwitching(null);
      setPending(null);
      refreshIbkrStatusNow();
    }
  }

  return (
    <div className={`gw-mode-capsule-wrap${className ? ` ${className}` : ''}`}>
      <div
        className={`gw-mode-capsule sv-capsule${selected ? ` is-${selected}` : ''}`}
        role="group"
        aria-label="Desk venue"
        data-testid={testId}
      >
        {VENUE_ORDER.map(v => (
          <button
            key={v}
            type="button"
            className={`gw-mode-capsule__seg sv-capsule__seg${
              selected === v ? ` is-selected is-${v}` : ''
            }`}
            aria-pressed={selected === v}
            disabled={switching !== null}
            data-why={switchingWhy}
            title={switchingWhy ? undefined : VENUE_TITLE[v]}
            data-testid={`${testId}-${v}`}
            onClick={() => void requestVenue(v)}
          >
            {switching === v ? '…' : VENUE_LABEL[v]}
          </button>
        ))}
      </div>
      {switchError ? (
        <div
          className="gw-mode-capsule__error"
          role="alert"
          data-testid={errorTestId ?? `${testId}-error`}
        >
          {switchError}
        </div>
      ) : null}
      {hintTarget && selected !== hintTarget && selected !== 'sim' ? (
        <div className="gw-mode-capsule__hint" data-testid={`${testId}-disconnect-hint`}>
          Gateway looks disconnected — try switching to {hintTarget}.
        </div>
      ) : null}
    </div>
  );
}
