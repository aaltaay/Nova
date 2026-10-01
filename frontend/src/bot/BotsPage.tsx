/**
 * The Bots page (approved mockup v4, ADR 027, ADR 042): your playbook, run by the bot --
 * what it watches, what it may risk, what it proposed and did. A shell page like
 * Account (nav rail -> NavPageHost), so it owns the whole view: the hero with the
 * master level, every gate, Activate and the kill switch; the strategies, each with
 * its own level; who trades and the risk sleeve; the proposals inbox, the activity
 * timeline and today's numbers. Nothing on this page places an order except through
 * the bot's own gated path, and nothing that keeps the bot from acting is hidden.
 */
import { useCallback, useRef } from 'react';
import {
  BOTS_PAGE_LOADING,
  BOTS_PAGE_SUB,
  BOTS_PAGE_TITLE,
  BOTS_SETUP_ROWS_POLL_MS,
  BOTS_STRATEGIES_ANCHOR,
  BOTS_VENUE_NAMES,
  botsDayLocked,
  botsSoftFired,
} from '../constantGroups/bots_page';
import { SAMPLE_BOT_ABSENT } from '../sample_data/sampleCopy';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { requestScannerTab } from '../workspace';
import { requestSetupsBoard, useSetupRows, useSetupsBoard } from '../setups';
import { BotActivity } from './BotActivity';
import { BotHero } from './BotHero';
import { strategySetups } from './botLevels';
import { BotProposalsInbox } from './BotProposalsInbox';
import { BotRiskCard } from './BotRiskCard';
import { BotsPageHeader } from './BotsPageHeader';
import { BotsStatusBar } from './BotsStatusBar';
import { BotStrategiesCard } from './BotStrategiesCard';
import { BotSymbolsCard } from './BotSymbolsCard';
import { BotTodayCard } from './BotTodayCard';
import { etTime, etUntil, usdCents } from './botWhen';
import { useBotArm } from './useBotArm';
import { useBotDayPnl } from './useBotDayPnl';
import { useBotPnlToday } from './useBotPnlToday';
import { useBotsVenue } from './useBotsVenue';
import { useKillSwitch } from './useKillSwitch';
import { useStockModes } from './useStockModes';
import type { BotSession } from './types';
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

/** The day lock and the bot trip on the desk venue, as banners: when, at what P&L, and until 04:00 ET. */
function BreakerBanners({ session }: { session: BotSession }) {
  const lock = session.day_lock;
  const soft = session.soft_breaker;
  const locked = lock?.active === true || session.day_lock_active;
  const venue = BOTS_VENUE_NAMES[String(lock?.venue ?? session.breakers?.venue ?? '')] ?? 'this venue';
  return (
    <>
      {locked ? (
        <div className="bots-banner bots-banner--hard" role="alert" data-testid="bots-day-lock-banner">
          {botsDayLocked(venue, etTime(lock?.tripped_at ?? null), usdCents(lock?.pnl ?? null),
            etUntil(lock?.until ?? session.hard_lock_until_date))}
        </div>
      ) : null}
      {(soft?.fired || session.soft_breaker_fired) && !locked ? (
        <div className="bots-banner" role="status" data-testid="bots-soft-banner">
          {botsSoftFired(etTime(soft?.at ?? null), usdCents(soft?.pnl ?? null), etUntil(soft?.until ?? null))}
        </div>
      ) : null}
    </>
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
  const symbolInput = useRef<HTMLInputElement>(null);

  // A bot stock's Level 2 opens pinned, so it never replaces the tab holding another line.
  const openPinned = useCallback((symbol: string) => openStockView(symbol, { pin: true }), [openStockView]);
  const showSetups = useCallback(() => {
    document.getElementById(BOTS_STRATEGIES_ANCHOR)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
                <BreakerBanners session={session} />
                <BotHero arm={arm} killSwitch={killSwitch} dayPnl={dayPnl}
                  onOpenL2={openPinned} onShowSetups={showSetups} onAddSymbol={focusSymbols} />
                <BotStrategiesCard session={session} busy={busy}
                  onSetupLevel={(id, n) => void patch({ setup_levels: { [id]: n } })}
                  onOpenBoard={openBoard} onOpenSymbol={openPinned} />
                <div className="bots-grid bots-grid--top">
                  <BotSymbolsCard session={session} modes={modes} onOpenL2={openPinned} inputRef={symbolInput} />
                  <BotRiskCard session={session} patch={patch} busy={busy} dayPnl={dayPnl} pnlParts={pnlParts} />
                </div>
                <div className="bots-grid bots-grid--bottom">
                  <BotProposalsInbox proposals={proposals} audit={audit} resolve={resolve} openTrader={openPinned} />
                  <BotActivity audit={audit} setupRows={setupRows} />
                  <BotTodayCard venue={venue} audit={audit} botPnl={botPnl} entries={session.entries_today}
                    firstAtStrategy={strategySetups(session)[0] ?? null} />
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
