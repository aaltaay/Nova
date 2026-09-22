/**
 * Account page (approved UX redesign, second slice). Follows the header venue
 * pills: Live shows the IBKR snapshot in the left column and states that the
 * history-driven panels have no practice ledger; Paper / Sim read Nova's
 * practice account and GET /api/practice/history. The old Account tab module
 * stays reachable as "Broker snapshot" (Live) and Reports is hosted as a tab
 * so nothing is lost.
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
import { BOT_MAX_SHARES_CAP } from '../constantGroups/bot';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { PRACTICE_VENUE_LABELS } from '../constantGroups/practice';
import { useIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import { isPracticeVenue } from '../practice/practiceAccountModel';
import { usePracticeAccount } from '../practice/practiceAccountResource';
import { useWorkspace } from '../workspace/WorkspaceContext';

const TradingTab = lazy(() => import('../ibkr/TradingTab').then((m) => ({ default: m.TradingTab })));

type PageTab = 'overview' | 'broker' | 'reports';

interface Props {
  onOpenTrader: (symbol: string) => void;
}

/** The venue the page follows: the header's venue, Live while disconnected. */
export function pageVenue(mode: string | null | undefined): DeskVenue {
  return isPracticeVenue(mode) ? mode : 'live';
}

export function AccountPage({ onOpenTrader }: Props) {
  const { ibkrMode, selectedSymbol, setSelectedSymbol, ibkrConnected } = useWorkspace();
  const venue = pageVenue(ibkrMode);
  const practiceVenue = isPracticeVenue(venue) ? venue : null;
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
  const today = todayPracticeDate();
  const hist = history.data && history.data.venue === practiceVenue ? history.data : null;
  const rows = accountDetailRows(figures, todayDailyRow(hist, today), hist != null);
  const absence = practiceVenue
    ? hist
      ? null
      : history.error
        ? `${ACCOUNT_HISTORY_UNAVAILABLE}: ${history.error}`
        : practiceVenue === 'sim' && ledger && !ledger.replay_key
          ? ACCOUNT_SIM_NOTHING_LOADED
          : ACCOUNT_HISTORY_LOADING
    : ACCOUNT_LIVE_NO_LEDGER;
  const breakers = session
    ? (() => {
        const tripped = (session.soft_breaker_fired ? 1 : 0) + (session.day_lock_active ? 1 : 0);
        return { tripped, armed: 2 - tripped };
      })()
    : null;
  const maxSharesCap = session?.caps?.max_shares ?? BOT_MAX_SHARES_CAP;
  const nowTs = Date.now() / 1000;
  const fills = hist?.fills ?? [];

  const tabs: Array<[PageTab, string]> = [
    ['overview', ACCOUNT_TAB_OVERVIEW],
    ...(venue === 'live' ? ([['broker', ACCOUNT_TAB_BROKER]] as Array<[PageTab, string]>) : []),
    ['reports', ACCOUNT_TAB_REPORTS],
  ];
  const activeTab: PageTab = tab === 'broker' && venue !== 'live' ? 'overview' : tab;

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
              {practiceVenue ? `${PRACTICE_VENUE_LABELS[practiceVenue]} · ${ledger?.account_id ?? '—'}` : 'Live · IBKR'}
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
              />
              <ComponentsPanel history={hist} absence={absence} range={range} />
              <LedgerPanel
                venue={venue}
                history={hist}
                absence={absence}
                accountId={ledger?.account_id ?? hist?.account_id ?? null}
                startingCash={ledger?.starting_cash ?? hist?.starting_cash ?? null}
              />
              <CalendarPanel history={hist} absence={absence} today={today} />
              <PositionsOrdersPanel
                practice={practiceVenue != null}
                positions={positions}
                working={ibkr.orders}
                closed={closedOrders}
                fills={fills}
              />
            </div>
          ) : (
            <div className="account-page__host" data-testid={`account-page-host-${activeTab}`}>
              <Suspense fallback={<TabLazyFallback />}>
                <TradingTab
                  selectedSymbol={selectedSymbol}
                  onSelectSymbol={setSelectedSymbol}
                  onOpenTrading={onOpenTrader}
                  initialSection={activeTab === 'reports' ? 'reports' : 'overview'}
                />
              </Suspense>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
