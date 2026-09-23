/**
 * The Bots page title row (approved mockup v4): the title, what the page is,
 * and whose money the bot would spend -- the venue, with the Sim playhead's
 * moment when the desk replays one.
 */
import {
  BOTS_PAGE_SAVING,
  BOTS_PAGE_SUB,
  BOTS_PAGE_TITLE,
  BOTS_VENUE_LABELS,
  BOTS_VENUE_NOTES,
  BOTS_VENUE_UNKNOWN,
} from '../constantGroups/bots_page';
import type { BotsVenue } from './useBotsVenue';

function playheadLabel(ts: number): string {
  const d = new Date(ts * 1000);
  const date = d.toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
  const time = d.toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false, hour: '2-digit', minute: '2-digit' });
  return `${date} ${time} ET`;
}

export function BotsPageHeader({ venue, busy }: { venue: BotsVenue; busy: boolean }) {
  const v = venue.venue;
  return (
    <header className="bots-page__head">
      <h1>{BOTS_PAGE_TITLE}</h1>
      <p className="bots-page__sub">{BOTS_PAGE_SUB}</p>
      {busy ? <span className="bots-page__saving">{BOTS_PAGE_SAVING}</span> : null}
      <div className="bots-page__venue" data-testid="bots-venue">
        {v ? (
          <>
            <span className={`bots-vchip bots-vchip--${v}`}>
              {BOTS_VENUE_LABELS[v]}{v === 'sim' && venue.playhead ? ` · ${playheadLabel(venue.nowTs)}` : ''}
            </span>
            <span className="bots-vchip">{BOTS_VENUE_NOTES[v]}</span>
          </>
        ) : (
          <span className="bots-vchip">{BOTS_VENUE_UNKNOWN}</span>
        )}
      </div>
    </header>
  );
}
