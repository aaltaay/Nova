/**
 * Account page (approved UX redesign, second slice). Follows the header venue
 * pills: Live shows the IBKR snapshot in the left column and states that the
 * history-driven panels have no practice ledger; Paper / Sim read Nova's
 * practice account and GET /api/practice/history. The old Account tab module
 * stays reachable as "Broker snapshot" (Live) and Reports is hosted as a tab
 * so nothing is lost -- neither hosts the Level 2 book or the order ticket,
 * which belong to the Trader (QA V23).
 *
 * The venue is the status's own `venue` (C26). On the sample desk the page
 * shows the Nova Marketing Sample Data account and polls nothing (V4).
 */
import { lazy, Suspense, useCallback, useMemo, useState } from 'react';
import '../account/account.css';
import '../account/account-panels.css';
import { AccountDetailsPanel } from '../account/AccountDetailsPanel';
import {
  accountDetailRows,
  todayDailyRow,
  todayPracticeDate,
} from '../account/accountFigures';
import { useAccountHistory } from '../account/accountHistoryResource';
import { liveCommissionsToday, liveFillRows, practiceFillRows } from '../account/accountLive';
import { positionsFromIbkr, positionsFromPractice } from '../account/accountPositions';
import { readAccountRangePref, writeAccountRangePref } from '../account/accountRangePref';
import { CalendarPanel } from '../account/CalendarPanel';
import { ComponentsPanel } from '../account/ComponentsPanel';
import { LedgerPanel } from '../account/LedgerPanel';
import { PerformancePanel, type PerfTab } from '../account/PerformancePanel';
import { PositionsOrdersPanel } from '../account/PositionsOrdersPanel';
import { useBotSession } from '../bot/useBotSession';
import { useClosedOrders } from '../closed_orders/useClosedOrders';
import { TabLazyFallback } from '../components/TabLazyFallback';
import { figuresFromPractice, figuresFromSummary } from '../components/headerAccountFigures';
import {
  ACCOUNT_HISTORY_LOADING,
  ACCOUNT_HISTORY_UNAVAILABLE,
  ACCOUNT_LIVE_NO_LEDGER,
  ACCOUNT_PAGE_TITLE,
  ACCOUNT_SIM_NOTHING_LOADED,
  ACCOUNT_TAB_BROKER,
  ACCOUNT_TAB_OVERVIEW,
  ACCOUNT_TAB_REPORTS,
  type AccountPerfMode,
  type AccountRange,
} from '../constantGroups/account_page';
import { BOT_HARD_BREAKER_USD, BOT_SOFT_BREAKER_USD } from '../constantGroups/bot';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { PRACTICE_VENUE_LABELS } from '../constantGroups/practice';
import { resolveDeskVenue } from '../ibkr/deskVenue';
import { useIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import type { TradingTabSection } from '../ibkr/TradingSectionNav';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { isPracticeVenue } from '../practice/practiceAccountModel';
import { usePracticeAccount } from '../practice/practiceAccountResource';
import { useSimAccountClock } from '../practice/useSimAccountClock';
import { SAMPLE_ACCOUNT_HISTORY_ABSENT, SAMPLE_MARKETING_LABEL } from '../sample_data/sampleCopy';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { useWorkspace } from '../workspace/WorkspaceContext';

const TradingTab = lazy(() => import('../ibkr/TradingTab').then((m) => ({ default: m.TradingTab })));

type PageTab = 'overview' | 'broker' | 'reports';

/** What each hosted tab offers of the old Account module: never its ticket or book (V23). */
const HOSTED_SECTIONS: Record<Exclude<PageTab, 'overview'>, readonly TradingTabSection[]> = {
  broker: ['overview'],
  reports: ['reports', 'activity', 'latency'],
};

interface Props {
  onOpenTrader: (symbol: string) => void;
}

/** The venue the page follows: the header's venue, Live while disconnected. */
export function pageVenue(mode: string | null | undefined): DeskVenue {
  return isPracticeVenue(mode) ? mode : 'live';
}

export function AccountPage({ onOpenTrader }: Props) {
  const { ibkrMode, selectedSymbol, setSelectedSymbol, ibkrConnected } = useWorkspace();
  const sampleDesk = useSampleRoute();
  const status = useIbkrStatus();
  // The sample desk's account is the sample IBKR-style summary; it never
  // selects a practice ledger or polls one (V4).
  const venue = sampleDesk ? 'live' : pageVenue(resolveDeskVenue(status, ibkrMode));
  const practiceVenue = !sampleDesk && isPracticeVenue(venue) ? venue : null;
  const ibkr = useIbkrAccountContext();
  const practice = usePracticeAccount(practiceVenue);
  const { orders: closedOrders } = useClosedOrders(ibkrConnected);
  const { session } = useBotSession();
  const [range, setRangeState] = useState<AccountRange>(readAccountRangePref);
  const [mode, setMode] = useState<AccountPerfMode>('pnl');
  const [perfTab, setPerfTab] = useState<PerfTab>('account');
  const [tab, setTab] = useState<PageTab>('overview');
  const [hidden, setHidden] = useState(false);
  const history = useAccountHistory(practiceVenue, range);
  // The calendar shows whole months whatever the Performance range (QA W5):
  // it reads every day the ledger (and its archives) hold.
  const calendarHistory = useAccountHistory(practiceVenue, 'ALL');

  const setRange = useCallback((next: AccountRange) => {
    setRangeState(next);
    writeAccountRangePref(next);
  }, []);

  const ledger = practiceVenue && practice.data?.venue === practiceVenue ? practice.data : null;
  const figures = ledger ? figuresFromPractice(ledger) : figuresFromSummary(ibkr.summary);
  const positions = useMemo(
    () => (ledger ? positionsFromPractice(ledger.positions) : positionsFromIbkr(ibkr.positions)),
    [ledger, ibkr.positions],
  );
  // Sim's day and "now" are the replay playhead's, never the browser's (C20 / V32).
  const simClock = useSimAccountClock(practiceVenue === 'sim');
  const nowTs = simClock.nowTs ?? Date.now() / 1000;
  const today = todayPracticeDate(new Date(nowTs * 1000));
  const loadedHist = history.data && history.data.venue === practiceVenue ? history.data : null;
  // Sim with nothing loaded and nothing traded: the panels say so instead of
  // drawing an empty ledger ("No fills in this range") -- C69.
  const simEmpty = simClock.nothingLoaded && !(Array.isArray(loadedHist?.fills) && loadedHist.fills.length > 0);
  const hist = simEmpty ? null : loadedHist;
  const loadedCalendar = calendarHistory.data && calendarHistory.data.venue === practiceVenue ? calendarHistory.data : null;
  const calendarHist = simEmpty ? null : loadedCalendar;
  // Live: commissions and fills are what IBKR reported on the session's orders (QA W17).
  const liveOrders = practiceVenue || sampleDesk ? [] : [...ibkr.orders, ...closedOrders];
  const rows = accountDetailRows(
    figures,
    todayDailyRow(hist, today),
    hist != null,
    practiceVenue ? null : liveCommissionsToday(liveOrders),
  );
  const historyAbsence = sampleDesk
    ? SAMPLE_ACCOUNT_HISTORY_ABSENT
    : practiceVenue
      ? hist
        ? null
        : history.error
          ? `${ACCOUNT_HISTORY_UNAVAILABLE}: ${history.error}`
          : practiceVenue === 'sim' && ledger && !ledger.replay_key
            ? ACCOUNT_SIM_NOTHING_LOADED
            : ACCOUNT_HISTORY_LOADING
      : ACCOUNT_LIVE_NO_LEDGER;
  const absence = simEmpty ? ACCOUNT_SIM_NOTHING_LOADED : historyAbsence;
  const calendarAbsence = calendarHist
    ? null
    : absence
      ?? (calendarHistory.error ? `${ACCOUNT_HISTORY_UNAVAILABLE}: ${calendarHistory.error}` : ACCOUNT_HISTORY_LOADING);
  const breakers = session
    ? (() => {
        const tripped = (session.soft_breaker_fired ? 1 : 0) + (session.day_lock_active ? 1 : 0);
        // ADR 032: the desk venue's own pair; an older API keeps the fixed defaults.
        return { tripped, armed: 2 - tripped, soft: session.breakers?.soft_usd ?? BOT_SOFT_BREAKER_USD,
          hard: session.breakers?.hard_usd ?? BOT_HARD_BREAKER_USD };
      })()
    : null;
  // The session's own cap, or none: the product ceiling is not this bot's cap (C35).
  const sessionCap = session?.caps?.max_shares;
  const maxSharesCap = typeof sessionCap === 'number' && Number.isFinite(sessionCap) ? sessionCap : null;
  const fills = practiceVenue ? practiceFillRows(hist?.fills ?? []) : liveFillRows(liveOrders);

  const tabs: Array<[PageTab, string]> = sampleDesk
    ? [['overview', ACCOUNT_TAB_OVERVIEW]]
    : [
        ['overview', ACCOUNT_TAB_OVERVIEW],
        ...(venue === 'live' ? ([['broker', ACCOUNT_TAB_BROKER]] as Array<[PageTab, string]>) : []),
        ['reports', ACCOUNT_TAB_REPORTS],
      ];
  const activeTab: PageTab = tabs.some(([id]) => id === tab) ? tab : 'overview';

  return (
    <div className="nova-shell nova-shell--scanner">
      <div className="main-col main-col--scanner-stack">
        <section className="account-page" aria-label={ACCOUNT_PAGE_TITLE} data-testid="account-page" data-venue={venue}>
          <div className="account-page__tabs" role="tablist">
            {tabs.map(([id, label]) => (
              <button key={id} type="button" role="tab" aria-selected={activeTab === id} className={`account-page__tab${activeTab === id ? ' is-on' : ''}`} data-testid={`account-page-tab-${id}`} onClick={() => setTab(id)}>
                {label}
              </button>
            ))}
            <span className="account-page__venue" data-testid="account-page-venue">
              {sampleDesk
                ? SAMPLE_MARKETING_LABEL
                : practiceVenue
                  ? `${PRACTICE_VENUE_LABELS[practiceVenue]} · ${ledger?.account_id ?? '—'}`
                  : 'Live · IBKR'}
            </span>
          </div>

          {activeTab === 'overview' ? (
            <div className="account-page__grid">
              <AccountDetailsPanel
                venue={venue}
                figures={figures}
                rows={rows}
                positions={positions}
                history={hist}
                range={range}
                onRange={setRange}
                breakers={breakers}
                maxSharesCap={maxSharesCap}
                hidden={hidden}
                onToggleHidden={() => setHidden((h) => !h)}
                nowTs={nowTs}
                // Sim with nothing loaded says so here too, not "has not answered yet" (D17).
                absence={sampleDesk ? SAMPLE_ACCOUNT_HISTORY_ABSENT : simEmpty ? ACCOUNT_SIM_NOTHING_LOADED : null}
                sample={sampleDesk}
              />
              <PerformancePanel
                history={hist}
                absence={absence}
                positions={positions}
                range={range}
                onRange={setRange}
                mode={mode}
                onMode={setMode}
                tab={perfTab}
                onTab={setPerfTab}
                nowTs={nowTs}
                netLiquidation={figures.netLiquidation}
                openPnl={figures.openPnl}
              />
              <ComponentsPanel history={hist} absence={absence} range={range} openPnl={figures.openPnl} />
              <LedgerPanel
                venue={venue}
                history={hist}
                absence={absence}
                accountId={ledger?.account_id ?? hist?.account_id ?? null}
                startingCash={ledger?.starting_cash ?? hist?.starting_cash ?? null}
              />
              <CalendarPanel history={calendarHist} absence={calendarAbsence} today={today} />
              <PositionsOrdersPanel
                practice={practiceVenue != null}
                venue={venue}
                positions={positions}
                working={ibkr.orders}
                closed={closedOrders}
                fills={fills}
                today={today}
              />
            </div>
          ) : (
            <div className="account-page__host" data-testid={`account-page-host-${activeTab}`}>
              <Suspense fallback={<TabLazyFallback />}>
                <TradingTab
                  key={activeTab}
                  selectedSymbol={selectedSymbol}
                  onSelectSymbol={setSelectedSymbol}
                  onOpenTrading={onOpenTrader}
                  initialSection={activeTab === 'reports' ? 'reports' : 'overview'}
                  sections={HOSTED_SECTIONS[activeTab === 'reports' ? 'reports' : 'broker']}
                  showTicket={false}
                />
              </Suspense>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
