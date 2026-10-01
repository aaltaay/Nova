/**
 * What every Nova buy may risk -- the sleeve, one per venue (ADR 042 E) -- and the
 * two loss breakers (approved mockup v4, ADR 032). The tabs pick the venue whose
 * sleeve you edit (the desk venue first); each slider PATCHes `{caps: {venue,
 * field}}` once let go. The breakers are the desk venue's own pair, dragged on their
 * bar, with what fired today and when it lifts (04:00 ET).
 */
import { useState } from 'react';
import {
  BOTS_RISK_LIVE_NOTE,
  BOTS_RISK_SUB,
  BOTS_RISK_TIP,
  BOTS_RISK_TITLE,
  BOTS_VENUE_NAMES,
} from '../constantGroups/bots_page';
import { tipProps } from '../ux/hoverTip';
import { BotBreakerBar } from './BotBreakerBar';
import { BotBreakerStatus } from './BotBreakerStatus';
import { BotSleeve } from './BotSleeve';
import type { BotCaps, BotSession } from './types';

type Patch = (body: Record<string, unknown>) => Promise<unknown>;

const VENUES = ['paper', 'sim', 'live'] as const;

/** The desk venue the session is the dial of, else Paper. */
function deskVenue(session: BotSession): string {
  return String(session.caps.venue ?? session.breakers?.venue ?? session.level_venue ?? 'paper');
}

/** That venue's sleeve; the desk venue's `caps` when the API keeps one sleeve for all. */
function capsFor(session: BotSession, venue: string): BotCaps {
  return session.caps_by_venue?.[venue] ?? session.caps;
}

export function BotRiskCard({ session, patch, busy, dayPnl, pnlParts = null }: {
  session: BotSession;
  patch: Patch;
  busy: boolean;
  dayPnl: number | null;
  /** How the day P&L the breakers compare was reached. */
  pnlParts?: string | null;
}) {
  const desk = deskVenue(session);
  const [picked, setPicked] = useState<string | null>(null);
  const venue = picked ?? desk;
  const perVenue = session.caps_by_venue != null;
  return (
    <section className="bots-card" data-testid="bots-risk">
      <header className="bots-card__head">
        <h3 {...tipProps(BOTS_RISK_TIP, BOTS_RISK_TITLE)}>{BOTS_RISK_TITLE}</h3>
        <span className="bots-card__sub">{BOTS_RISK_SUB}</span>
      </header>
      {perVenue ? (
        <div className="bots-chips bots-sleeve__venues" role="tablist" aria-label="Sleeve venue">
          {VENUES.map(v => (
            <button key={v} type="button" role="tab" aria-selected={venue === v}
              className={`bots-fchip${venue === v ? ' is-on' : ''}`} data-testid={`bots-sleeve-tab-${v}`}
              onClick={() => setPicked(v)}>
              {BOTS_VENUE_NAMES[v]}{v === desk ? ' · desk' : ''}
            </button>
          ))}
        </div>
      ) : null}
      {venue === 'live' ? <p className="bots-muted bots-sleeve__note">{BOTS_RISK_LIVE_NOTE}</p> : null}
      <BotSleeve key={venue} venue={venue} caps={capsFor(session, venue)} capsBounds={session.caps_bounds}
        busy={busy} patch={patch} />

      <BotBreakerBar breakers={session.breakers} dayPnl={dayPnl} pnlParts={pnlParts} busy={busy} patch={patch} />
      <BotBreakerStatus session={session} />
    </section>
  );
}
