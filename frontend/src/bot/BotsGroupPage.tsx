/**
 * Bots itself, the parent of LiveTrader Bots and Strategy Bots in the nav rail: empty for now (operator, 2026-10-15:
 * "keep it empty for now"), so it only points at its two children.
 */
import { BOTS_GROUP_EMPTY, BOTS_GROUP_TITLE } from '../constantGroups/bots_page';
import './botsPage.css';

export function BotsGroupPage() {
  return (
    <div className="nova-shell nova-shell--scanner">
      <div className="main-col main-col--scanner-stack">
        <div className="bots-page" data-testid="bots-group-page">
          <div className="bots-page__scroll">
            <header className="bots-page__head">
              <h1>{BOTS_GROUP_TITLE}</h1>
            </header>
            <p className="bots-empty" role="status">{BOTS_GROUP_EMPTY}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
