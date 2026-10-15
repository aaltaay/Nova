/**
 * Bots > LiveTrader Bots (operator decision 2026-10-15): the LiveTrader Bots key on top, then the Live Traders panel
 * (ADR 055) as it was -- one card per TraderTV host, each with its own Bot key. A host's bot places orders only while
 * the header's Bot switch, this key and its own key are all on; every block is said on the panel's blocker line, so the
 * family never needs a switch that lives on another page. A shell page (nav rail -> NavPageHost). The sample desk has
 * no bot: a stated absence, and nothing here polls.
 */
import { BOTS_PAGE_SUB, LT_BOTS_PAGE_TITLE } from '../constantGroups/bots_page';
import { SAMPLE_BOT_ABSENT } from '../sample_data/sampleCopy';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { BotFamilyKey } from './BotFamilyKey';
import { BotLiveTradersCard } from './BotLiveTradersCard';
import './botsPage.css';

export function LiveTraderBotsPage() {
  const sample = useSampleRoute();
  return (
    <div className="nova-shell nova-shell--scanner">
      <div className="main-col main-col--scanner-stack">
        <div className="bots-page" data-testid="bots-live-trader-page">
          <div className="bots-page__scroll">
            <header className="bots-page__head">
              <h1>{LT_BOTS_PAGE_TITLE}</h1>
              {sample ? <p className="bots-page__sub">{BOTS_PAGE_SUB}</p> : null}
            </header>
            {sample ? (
              <p className="bots-empty bots-page__loading" role="status">{SAMPLE_BOT_ABSENT}</p>
            ) : (
              <>
                <BotFamilyKey family="live_trader" />
                <BotLiveTradersCard />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
