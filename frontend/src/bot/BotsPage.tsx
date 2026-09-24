/**
 * The Bots page (approved mockup v4, ADR 027): your playbook, run by the bot --
 * what it watches, what it may risk, what it proposed and did. A shell page
 * like Account (nav rail -> NavPageHost), so it owns the whole view: the hero
 * with the level, every gate and Activate / the kill switch; the strategies,
 * symbols and risk sleeve; the proposals inbox, the activity timeline and
 * today's scoreboard. Nothing on this page places an order except through the
 * bot's own gated path.
 */
import { useCallback, useRef } from 'react';
import { BOT_HARD_BREAKER_USD, BOT_SOFT_BREAKER_USD } from '../constantGroups/bot';
import { BOTS_PAGE_LOADING, BOTS_PAGE_SUB, BOTS_PAGE_TITLE, BOTS_SETUP_ROWS_POLL_MS } from '../constantGroups/bots_page';
import { SAMPLE_BOT_ABSENT } from '../sample_data/sampleCopy';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { requestScannerTab } from '../workspace';
import { requestSetupsBoard, useSetupRows, useSetupsBoard } from '../setups';
import { BotActivity } from './BotActivity';
import { BotHero } from './BotHero';
import { BotProposalsInbox } from './BotProposalsInbox';
import { BOTS_READOUT_ANCHOR } from './BotReadout';
import { BotRiskCard } from './BotRiskCard';
import { BotsPageHeader } from './BotsPageHeader';
import { BotsStatusBar } from './BotsStatusBar';
import { BotStrategiesCard } from './BotStrategiesCard';
import { BotSymbolsCard } from './BotSymbolsCard';
import { BotTodayCard } from './BotTodayCard';
import { fmtUsd } from './botsPageFormat';
import { useBotArm } from './useBotArm';
import { useBotDayPnl } from './useBotDayPnl';
import { useBotPnlToday } from './useBotPnlToday';
import { useBotsVenue } from './useBotsVenue';
import { useKillSwitch } from './useKillSwitch';
import './botsPage.css';
import './botsPageCards.css';

export function BotsPage() {
  // V4: the sample desk has no bot -- a stated absence, and nothing here polls.
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
  const { session, proposals, audit, error, busy, patch, resolve, onLevel } = arm;
  const { openStockView } = useWorkspace();
  const killSwitch = useKillSwitch();
  const { pnl: dayPnl } = useBotDayPnl(session != null);
  const venue = useBotsVenue();
  const botPnl = useBotPnlToday(venue.practiceVenue, venue.today);
  const board = useSetupsBoard()?.board;
  const { rows: setupRows } = useSetupRows(board?.session_date ?? venue.today, BOTS_SETUP_ROWS_POLL_MS);
  const symbolInput = useRef<HTMLInputElement>(null);

  // A bot symbol's Level 2 opens pinned, so it never replaces the tab holding another line.
  const openPinned = useCallback((symbol: string) => openStockView(symbol, { pin: true }), [openStockView]);
  const showReadout = useCallback(() => {
    document.getElementById(BOTS_READOUT_ANCHOR)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, []);
  const focusSymbols = useCallback(() => {
    symbolInput.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    symbolInput.current?.focus();
  }, []);
  // A setup card's "Open board": Watchlist › Setups, filtered to that setup (ADR 031).
  const openBoard = useCallback((setup: string) => {
    requestSetupsBoard(setup);
    requestScannerTab('watchlist');
  }, []);
  const soft = session?.breakers?.soft_usd ?? BOT_SOFT_BREAKER_USD;
  const hard = session?.breakers?.hard_usd ?? BOT_HARD_BREAKER_USD;

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
                {session.day_lock_active ? (
                  <div className="bots-banner bots-banner--hard" role="alert">
                    {fmtUsd(hard)} day lock is on. Bot and manual buys stay blocked until midnight
                    America/New_York ({session.hard_lock_until_date}). Flatten / kill still work.
                  </div>
                ) : null}
                {session.soft_breaker_fired && !session.day_lock_active ? (
                  <div className="bots-banner" role="status">
                    The {fmtUsd(soft)} bot trip flattened the account and dropped the bot to L0. The desk can
                    still trade. Activate re-enables it.
                  </div>
                ) : null}
                <BotHero arm={arm} killSwitch={killSwitch} dayPnl={dayPnl}
                  onOpenL2={openPinned} onReadout={showReadout} onAddSymbol={focusSymbols} />
                <BotStrategiesCard session={session} busy={busy}
                  onChooseSetup={id => void patch({ setup: id })} onLevel={n => void onLevel(n)}
                  onSetupLevel={(id, n) => void patch({ setup_levels: { [id]: n } })}
                  onOpenBoard={openBoard} onOpenSymbol={openPinned} />
                <div className="bots-grid bots-grid--top">
                  <BotSymbolsCard session={session} onOpenL2={openPinned} inputRef={symbolInput} />
                  <BotRiskCard session={session} patch={patch} busy={busy} dayPnl={dayPnl} />
                </div>
                <div className="bots-grid bots-grid--bottom">
                  <BotProposalsInbox proposals={proposals} audit={audit} resolve={resolve} openTrader={openPinned} />
                  <BotActivity audit={audit} setupRows={setupRows} />
                  <BotTodayCard venue={venue} audit={audit} botPnl={botPnl} setup={session.setup} />
                </div>
              </>
            )}
          </div>
          {session ? <BotsStatusBar session={session} /> : null}
        </div>
      </div>
    </div>
  );
}
