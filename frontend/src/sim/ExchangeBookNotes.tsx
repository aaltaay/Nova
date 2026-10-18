/**
 * The replay ladder's words for an exchange's own book imported for the day (ADR 057).
 *
 * Such a book is one venue's orders -- Nasdaq's book holds only what rests on Nasdaq -- so everything here names
 * the venue and says it is not the whole market: the note over the ladder (whose book, when it last changed), the
 * banner under it (what was imported and the span it covers), and a gap the venue flagged in its own feed. Where
 * books were imported but none covers the playhead, the absence is stated with the span they do cover; nothing is
 * drawn in their place.
 */
import { etTime } from './historicalReplayFormat';
import type { ExchangeBookCoverage, HistoricalDepthBook } from './historicalTypes';
import {
  SIM_REPLAY_L2_VENUE_UNNAMED,
  simReplayL2VenueAbsent,
  simReplayL2VenueCovers,
  simReplayL2VenueElsewhere,
  simReplayL2VenueGap,
  simReplayL2VenueNote,
  simReplayL2VenueTitle,
} from './simConstants';

/** "Nasdaq", or "Nasdaq + NYSE Arca": the venues' names, in the order the backend lists them. */
export const venueNames = (labels: string[]): string => labels.join(' + ');

/** The venues of the book shown; a book whose venues did not parse still reads as one exchange's, never the market's. */
export const venueLabels = (depth: HistoricalDepthBook): string[] => {
  const labels = (depth.venues ?? []).map(venue => venue.label);
  return labels.length ? labels : [SIM_REPLAY_L2_VENUE_UNNAMED];
};

/** HH:MM for a whole minute (04:00), HH:MM:SS otherwise (19:59:58): the banner fits the rail's narrow ladder. */
const clock = (ts: number): string => etTime(ts).replace(/^(\d\d:\d\d):00$/, '$1');
const span = (book: ExchangeBookCoverage): string => `${clock(book.known_from)}–${clock(book.known_to)}`;

/** Each book's span; a single book's span alone, several each after its venue's name. */
function spans(books: ExchangeBookCoverage[]): string {
  return books.length === 1 ? span(books[0]) : books.map(book => `${book.label} ${span(book)}`).join(' · ');
}

/** Over the ladder while a venue book covers the playhead. */
export function ExchangeBookNote({ depth }: { depth: HistoricalDepthBook }) {
  const labels = venueLabels(depth);
  const names = venueNames(labels);
  return (
    <div className="sim-replay-l2-note" data-testid="historical-l2-exchange" title={simReplayL2VenueTitle(names)}>
      {simReplayL2VenueNote(names, labels.length > 1, etTime(depth.ts))}
    </div>
  );
}

/** Inside an empty ladder: books were imported for the day, and none covers this moment. */
export function exchangeBookAbsence(books: ExchangeBookCoverage[]): string | null {
  return books.length ? simReplayL2VenueAbsent(venueNames(books.map(book => book.label))) : null;
}

/** Under the note: what was imported for the day and the span it covers, whatever the ladder shows now. */
export function ExchangeBookBanner({ books, showing }: { books: ExchangeBookCoverage[]; showing: boolean }) {
  if (!books.length) return null;
  const names = venueNames(books.map(book => book.label));
  return (
    <div className="sim-replay-l2-coverage" data-testid="historical-l2-coverage" title={simReplayL2VenueTitle(names)}>
      {showing ? simReplayL2VenueCovers(spans(books), books.length > 1)
        : simReplayL2VenueElsewhere(spans(books), books.length > 1)}
    </div>
  );
}

/** A gap the venue flagged in its own feed at the event shown: its book there may be missing orders. */
export function ExchangeBookGap({ depth }: { depth: HistoricalDepthBook }) {
  const flagged = (depth.venues ?? []).filter(venue => venue.maybe_bad_book);
  if (!flagged.length) return null;
  return (
    <div className="sim-replay-l2-warning" role="status" data-testid="historical-l2-bad-book">
      {flagged.map(venue => simReplayL2VenueGap(venue.label)).join(' · ')}
    </div>
  );
}
