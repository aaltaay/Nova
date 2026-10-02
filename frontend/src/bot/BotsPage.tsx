/**
 * The Bots page (ADR 043, approved mockup v8): everything that decides whether Nova buys, on one page.
 * Top to bottom: "Can Nova buy right now?" in one line for every ticker; the Bot card (the one switch,
 * Freeze all orders, what the bot may risk); the strategies, each Off / Eyes / On with its bot rules;
 * IBKR's Level 2 lines and lending; Tickers today (the hot list and the squares by ticker); then today's
 * numbers, the proposals and the activity. A shell page like Account (nav rail -> NavPageHost). Nothing
 * here places an order except through the bot's own gated path, and nothing that keeps Nova from
 * buying is hidden.
 */
import { useCallback } from 'react';
import {
  BOTS_PAGE_LOADING,
  BOTS_PAGE_SUB,
  BOTS_PAGE_TITLE,
  BOTS_SETUP_ROWS_POLL_MS,
  BOTS_STRATEGIES_ANCHOR,
} from '../constantGroups/bots_page';
import { SAMPLE_BOT_ABSENT } from '../sample_data/sampleCopy';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { useTradingPinGate } from '../ibkr/useTradingPinGate';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { requestScannerTab } from '../workspace';
import { requestSetupsBoard, useSetupRows, useSetupsBoard } from '../setups';
import { BotActivity } from './BotActivity';
import { BotAnswerLine } from './BotAnswerLine';
import { gateContext } from './botGateWords';
import { strategySetups } from './botLevels';
import { BotLinesCard } from './BotLinesCard';
import { BotProposalsInbox } from './BotProposalsInbox';
import { BotBreakerBlock, BotRiskCard } from './BotRiskCard';
import { BotsPageHeader } from './BotsPageHeader';
import { BotsStatusBar } from './BotsStatusBar';
import { BotStrategiesCard } from './BotStrategiesCard';
import { BotSwitchCard } from './BotSwitchCard';
import { BotTickersTable, useTriggers } from './BotTickersTable';
import { BotTodayCard } from './BotTodayCard';
import { useBotArm } from './useBotArm';
import { useBotDayPnl } from './useBotDayPnl';
import { useBotPnlToday } from './useBotPnlToday';
import { useBotsVenue } from './useBotsVenue';
import { useKillSwitch } from './useKillSwitch';
import { useStockModes } from './useStockModes';
import './botsPage.css';
import './botsPageCards.css';
import './botsOnePage.css';

export function BotsPage() {
  // The sample desk has no bot -- a stated absence, and nothing here polls.
  return useSampleRoute() ? <BotsSampleAbsence /> : <LiveBotsPage />;
}

function BotsSampleAbsence() {
  return (
    <div className="nova-shell nova-shell--scanner">
      <div className="main-col main-col--scanner-stack">
        <div className="bots-page" data-testid="bots-page">
          <header className="bots-page__head">
            <h1>{BOTS_PAGE_TITLE}</h1>
            <p className="bots-page__sub">{BOTS_PAGE_SUB}</p>
          </header>
          <p className="bots-empty bots-page__loading" role="status">{SAMPLE_BOT_ABSENT}</p>
        </div>
      </div>
    </div>
  );
}

function LiveBotsPage() {
  const arm = useBotArm();
  const { session, proposals, audit, error, busy, patch, resolve } = arm;
  const { openStockView } = useWorkspace();
  const killSwitch = useKillSwitch();
  const { pnl: dayPnl, parts: pnlParts } = useBotDayPnl(session != null);
  const venue = useBotsVenue();
  const botPnl = useBotPnlToday(venue.practiceVenue, venue.today);
  const modes = useStockModes(session != null);
  const board = useSetupsBoard()?.board;
  const { rows: setupRows } = useSetupRows(board?.session_date ?? venue.today, BOTS_SETUP_ROWS_POLL_MS);
  const today = useTriggers(null, session != null);
  const { ensureUnlocked, pinDialog } = useTradingPinGate();

  // A stock's Level 2 opens pinned, so it never replaces the tab holding another line.
  const openPinned = useCallback((symbol: string) => openStockView(symbol, { pin: true }), [openStockView]);
  // A setup card's "Open board": Watchlist › Setups, filtered to that setup (ADR 031).
  const openBoard = useCallback((setup: string) => {
    requestSetupsBoard(setup);
    requestScannerTab('watchlist');
  }, []);

  return (
    <div className="nova-shell nova-shell--scanner">
      <div className="main-col main-col--scanner-stack">
        <div className="bots-page" data-testid="bots-page">
          <div className="bots-page__scroll">
            <BotsPageHeader venue={venue} busy={busy} />
            {!session ? (
              <p className="bots-empty bots-page__loading" role="status">{error || BOTS_PAGE_LOADING}</p>
            ) : (
              <>
                <BotAnswerLine session={session} ctx={gateContext(session, dayPnl)} triggers={today.view}
                  strategiesAnchor={BOTS_STRATEGIES_ANCHOR} onUnlock={() => void ensureUnlocked()} />
                <BotSwitchCard arm={arm} killSwitch={killSwitch}
                  breakers={<BotBreakerBlock session={session} patch={patch} busy={busy} dayPnl={dayPnl} pnlParts={pnlParts} />}>
                  <BotRiskCard session={session} patch={patch} busy={busy} dayPnl={dayPnl} pnlParts={pnlParts} breakers={false} />
                </BotSwitchCard>
                <BotStrategiesCard session={session} busy={busy}
                  onSetupLevel={(id, n) => void patch({ setup_levels: { [id]: n } })}
                  onOpenBoard={openBoard} onOpenSymbol={openPinned} />
                <BotLinesCard />
                <BotTickersTable today={today} modes={modes.rows} onModesChanged={modes.refresh}
                  boardRows={board?.rows ?? []} onOpenSymbol={openPinned} />
                <div className="bots-grid bots-grid--last">
                  <div className="bots-stack">
                    <BotTodayCard venue={venue} audit={audit} botPnl={botPnl} entries={session.entries_today}
                      firstAtStrategy={strategySetups(session)[0] ?? null} />
                    <BotProposalsInbox proposals={proposals} audit={audit} resolve={resolve} openTrader={openPinned} />
                  </div>
                  <div className="bots-activity-col"><BotActivity audit={audit} setupRows={setupRows} /></div>
                </div>
              </>
            )}
          </div>
          {session ? <BotsStatusBar session={session} /> : null}
          {pinDialog}
        </div>
      </div>
    </div>
  );
}
