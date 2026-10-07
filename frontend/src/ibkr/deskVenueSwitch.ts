/**
 * Switch the desk venue (ADR 020): the one door the header's Paper | Live | Sim pills and an
 * agent's show (ADR 050) both go through. POST /api/desk/venue {venue}; Sim falls back to the
 * legacy POST /api/sim when the venue route is missing (stale API process); Live keeps ensuring
 * the live Gateway. Leaving a venue cancels Nova's working entries there first (ADR 042 F): the
 * answer's `left` lists them, and each is a bot notice in this window. A later confirmed
 * transition (another window, a status read) wins over this request's reply.
 */
import { novaFetch } from '../api/novaFetch';
import { noticeVenueLeft } from '../bot';
import {
  API_BASE_URL,
  DESK_VENUE_API_PATH,
  DESK_VENUE_API_RESTART_HINT,
  DESK_VENUE_GATEWAY_MODE_API_PATH,
  DESK_VENUE_SIM_FALLBACK_API_PATH,
  deskVenueSwitchFailed,
  GATEWAY_MODE_API_RESTART_HINT,
} from '../constants';
import type { DeskVenue } from '../constantGroups/desk_venue';
import {
  confirmDeskVenue,
  getConfirmedDeskVenueRevision,
  getConfirmedDeskVenueStoreSnapshot,
  isConfirmedDeskVenueStoreSnapshotCurrent,
  subscribeConfirmedDeskVenueStore,
  type ConfirmedDeskVenueSnapshot,
} from './confirmedDeskVenueStore';
import { watchDeskRequestRoute } from './deskRequestRouteFence';
import { refreshIbkrAccountNow } from './ibkrAccountPoller';
import type { IbkrMode } from './types';
import { refreshIbkrStatusNow } from './useIbkrStatus';

interface VenueResponse {
  ok?: boolean;
  error?: string | null;
  detail?: string;
  venue?: DeskVenue;
  mode?: IbkrMode;
  launch_action?: string | null;
  message?: string | null;
  sim?: boolean;
  /** ADR 042 F: Nova's working entries cancelled on the venue the desk left. */
  left?: unknown;
}

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

/**
 * Move the desk to `next`. Resolves null when it moved (or a later transition owns the venue now),
 * else the reason in words. Throws only when Nova cannot be reached.
 */
export async function switchDeskVenue(next: DeskVenue): Promise<string | null> {
  const route = watchDeskRequestRoute();
  let askedRevision = getConfirmedDeskVenueRevision();
  let confirmedScope: ConfirmedDeskVenueSnapshot | null = null;
  let awaitingConfirmation = true;
  let invalidated = false;
  const offVenue = subscribeConfirmedDeskVenueStore(() => {
    const observed = getConfirmedDeskVenueStoreSnapshot();
    // Status may see this switch before its POST reply. Accept only that
    // first requested transition; any competing or later/ABA transition wins.
    if (invalidated) return;
    if (!awaitingConfirmation || confirmedScope || observed.venue !== next) {
      invalidated = true;
      return;
    }
    confirmedScope = observed;
    askedRevision = getConfirmedDeskVenueRevision();
  });
  const isCurrent = () => !invalidated && route.isCurrent() && askedRevision === getConfirmedDeskVenueRevision()
    && (!confirmedScope || isConfirmedDeskVenueStoreSnapshotCurrent(confirmedScope));
  try {
    const [res, body] = await postJson(DESK_VENUE_API_PATH, { venue: next });
    if (!route.isCurrent()) return null;
    // Cancellations already happened, even if another window now owns the
    // venue. Report their facts without accepting this reply's stale state.
    noticeVenueLeft(body.left);
    // A later confirmed transition wins even if this older POST answered successfully.
    // Check before state publication or any follow-on Gateway write.
    if (!isCurrent()) return null;
    if (isRouteMissing(res, body)) {
      if (next !== 'sim') return DESK_VENUE_API_RESTART_HINT;
      const message = await legacySimFallback();
      return isCurrent() ? message : null;
    }
    if (!res.ok || body.venue !== next) {
      return switchErrorMessage(res, body, next, DESK_VENUE_API_RESTART_HINT);
    }
    // An early status confirmation already owns its generation. Do not
    // republish the older reply, but still ensure the requested Live Gateway.
    if (!confirmedScope) {
      confirmDeskVenue(body.venue);
      confirmedScope = getConfirmedDeskVenueStoreSnapshot();
      askedRevision = getConfirmedDeskVenueRevision();
    }
    awaitingConfirmation = false;
    if (next !== 'live' || !isCurrent()) return null;
    const message = await ensureLiveGateway();
    return isCurrent() ? message : null;
  } catch (error) {
    if (!isCurrent()) return null;
    throw error;
  } finally {
    offVenue();
    route.dispose();
  }
}

/**
 * `switchDeskVenue`, then the status and the account read now -- as the pills do once a switch
 * settles, so the old venue's orders and positions never linger on screen.
 */
export async function moveDeskToVenue(next: DeskVenue): Promise<string | null> {
  try {
    return await switchDeskVenue(next);
  } finally {
    refreshIbkrStatusNow();
    refreshIbkrAccountNow();
  }
}
