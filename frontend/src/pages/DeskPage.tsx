/**
 * Desk placeholder -- the Scanner + Trader hybrid is the next slice of the
 * approved UX redesign. One calm panel, nothing fabricated.
 */
import { DESK_PAGE_PLACEHOLDER, DESK_PAGE_TITLE } from '../constantGroups/nav_rail';
import '../styles/rail-pages.css';

export function DeskPage() {
  return (
    <div className="nova-shell nova-shell--scanner">
      <div className="main-col main-col--scanner-stack">
        <section className="panel rail-page rail-page--desk" aria-label={DESK_PAGE_TITLE} data-testid="desk-page">
          <p className="rail-page__calm">{DESK_PAGE_PLACEHOLDER}</p>
        </section>
      </div>
    </div>
  );
}
