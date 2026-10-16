/**
 * Bots > LiveTrader Bots (operator, 2026-10-15: "i want all content from the original tradertv live to be inside
 * livetrader bots"; approved from a render): the followed traders' page -- the TraderTV hosts, what they hold and
 * closed, the stream and the Activity -- with the LiveTrader Bots key in its head and each host's bot (ADR 055) in the
 * middle of their card. A host's bot places orders only while the header's Bot switch, this key and its own key are
 * all on, and the head says which is off. A shell page (nav rail -> NavPageHost). The sample desk has no bot and no
 * feed: a stated absence, and nothing here polls. Under the hosts, the desk's Positions / Orders · today dock -- the
 * Scanner's own, resizable and collapsible (operator ask 2026-10-16: "I do want to see the positions tab").
 */
import { BOTS_PAGE_SUB, LT_BOTS_PAGE_TITLE } from '../constantGroups/bots_page';
import { FollowedTradersPage, type FollowedSlots } from '../followed_traders';
import { ScannerDesk } from '../scanner';
import { SAMPLE_BOT_ABSENT } from '../sample_data/sampleCopy';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { LiveTraderBadge } from './LiveTraderBadge';
import { LiveTraderHead } from './LiveTraderHead';
import { LiveTraderStrip } from './LiveTraderStrip';
import './botsPage.css';

const SLOTS: FollowedSlots = { Head: LiveTraderHead, Trader: LiveTraderStrip, OpenBadge: LiveTraderBadge };

export function LiveTraderBotsPage({ onOpenTrader }: { onOpenTrader?: (symbol: string) => void }) {
  const sample = useSampleRoute();
  if (!sample) {
    return (
      <ScannerDesk host="bots" onOpenTrading={onOpenTrader}>
        <FollowedTradersPage onOpenTrader={onOpenTrader} slots={SLOTS} />
      </ScannerDesk>
    );
  }
  return (
    <div className="nova-shell nova-shell--scanner">
      <div className="main-col main-col--scanner-stack">
        <div className="bots-page" data-testid="bots-live-trader-page">
          <div className="bots-page__scroll">
            <header className="bots-page__head">
              <h1>{LT_BOTS_PAGE_TITLE}</h1>
              <p className="bots-page__sub">{BOTS_PAGE_SUB}</p>
            </header>
            <p className="bots-empty bots-page__loading" role="status">{SAMPLE_BOT_ABSENT}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
