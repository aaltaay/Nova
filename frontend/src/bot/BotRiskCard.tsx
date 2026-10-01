/**
 * What every Nova buy may risk -- the sleeve, one per venue (ADR 042 E) -- and the
 * two loss breakers (approved mockup v4, ADR 032). The tabs pick the venue whose
 * sleeve you edit (the desk venue first); each slider PATCHes `{caps: {venue,
 * field}}` once let go. The breakers are the desk venue's own pair, dragged on their
 * bar, with what fired today and when it lifts (04:00 ET). Advise's budget stays here,
 * folded away, only while the API still keeps one -- it reads, it never places.
 */
import { useState } from 'react';
import {
  BOTS_ADVISE_TITLE,
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

function AdviseBudget({ session, patch }: { session: BotSession; patch: Patch }) {
  const advise = session.advise;
  if (!advise) return null;
  return (
    <details className="bots-advise">
      <summary>{BOTS_ADVISE_TITLE}</summary>
      <label className="bots-switch">
        <input type="checkbox" role="switch" data-testid="bot-strategy-advise-enabled" checked={advise.enabled}
          aria-checked={advise.enabled} onChange={e => void patch({ advise: { enabled: e.target.checked } })} />
        <span className="bots-switch__track" aria-hidden="true" />
        <span>Enable Advise for the bot</span>
      </label>
      <div className="bots-advise__caps">
        <label>
          <span>USD cap</span>
          <input type="number" data-testid="bot-strategy-advise-usd" min={0} step={0.25} defaultValue={advise.usd_cap}
            key={`usd-${advise.usd_cap}`}
            onBlur={e => { const v = Number(e.target.value); if (Number.isFinite(v) && v >= 0 && v !== advise.usd_cap) void patch({ advise: { usd_cap: v } }); }} />
        </label>
        <label>
          <span>Call cap</span>
          <input type="number" data-testid="bot-strategy-advise-calls" min={0} step={1} defaultValue={advise.call_cap}
            key={`calls-${advise.call_cap}`}
            onBlur={e => { const v = Number(e.target.value); if (Number.isInteger(v) && v >= 0 && v !== advise.call_cap) void patch({ advise: { call_cap: v } }); }} />
        </label>
        <span className="bots-muted">Spent ${advise.usd_spent.toFixed(2)} · {advise.calls_used} calls</span>
      </div>
    </details>
  );
}

export function BotRiskCard({ session, patch, busy, dayPnl }: {
  session: BotSession;
  patch: Patch;
  busy: boolean;
  dayPnl: number | null;
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

      <BotBreakerBar breakers={session.breakers} dayPnl={dayPnl} busy={busy} patch={patch} />
      <BotBreakerStatus session={session} />

      <AdviseBudget session={session} patch={patch} />
    </section>
  );
}
