/**
 * Compact account cluster for GlobalAppBar, in Webull's order:
 *   Day's: +$12.34 +0.12% ▾ | Working: 0 ▾ | TAV: $100,000.00 ▾ | Individual Margin (U1234567) ▾
 * One row on every venue. Live reads the IBKR summary; Paper / Sim read Nova's
 * practice ledger, which is THE account there even though Paper runs on the
 * live Gateway (ADR 020). Separate from the GATEWAY market-data chip -- never
 * label "IBKR offline" while Gateway is up (globalBarAccountChrome).
 */
import { useEffect, useId, useRef, useState } from 'react';
import type { ClosedOrder } from '../closed_orders/types';
import {
  GLOBAL_BAR_ACCOUNT_LOADING_CHIP,
  GLOBAL_BAR_ACCOUNT_LOADING_TITLE,
  GLOBAL_BAR_ACCOUNT_UNAVAILABLE_CHIP,
  GLOBAL_BAR_ACCOUNT_UNAVAILABLE_TITLE,
  GLOBAL_BAR_DAY_PNL_TITLE,
  GLOBAL_BAR_OFFLINE_CHIP,
  GLOBAL_BAR_OFFLINE_PLACEHOLDER,
  GLOBAL_BAR_TAV_LABEL,
  GLOBAL_BAR_TAV_TITLE,
  GLOBAL_BAR_WORKING_LABEL,
  GLOBAL_BAR_WORKING_MENU_TITLE,
} from '../constantGroups/global_bar';
import {
  PRACTICE_ACCOUNT_LOADING,
  PRACTICE_ACCOUNT_UNAVAILABLE,
  practiceDayPnlTitle,
  practiceTavTitle,
} from '../constantGroups/practice';
import type { IbkrAccountSummary, IbkrMode, IbkrOrder } from '../ibkr/types';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { isPracticeVenue } from '../practice/practiceAccountModel';
import { usePracticeAccount } from '../practice/practiceAccountResource';
import { AccountPillButton, AccountPillMenu } from './GlobalBarAccountPill';
import { DayPnlButton, DayPnlCard } from './GlobalBarDayPnl';
import { TavButton, TavCard } from './GlobalBarTav';
import { GlobalWorkingMenu } from './GlobalWorkingMenu';
import { resolvePracticeChromeState, type AccountChromeState } from './globalBarAccountChrome';
import { formatSignedMoney } from './globalBarMoney';
import { figuresFromPractice, figuresFromSummary } from './headerAccountFigures';
import { headerAccountPillView } from './headerAccountPill';

type ClusterMenu = 'day' | 'tav' | 'working' | 'pill' | null;

interface Props {
  /** IBKR account chrome from GlobalAppBar; the practice venues follow their own poll instead. */
  accountChrome: AccountChromeState;
  accountError: string | null;
  summary: IbkrAccountSummary | null;
  orders: IbkrOrder[];
  closedOrders: ClosedOrder[];
  traderActive: boolean;
  closeTraderView: () => void;
  refresh: () => void;
  /** Desk venue (ADR 020): live = the IBKR account; paper / sim = Nova's practice ledger. */
  venue?: IbkrMode | null;
}

function offlineChip(
  chrome: Exclude<AccountChromeState, 'ready'>,
  practice: boolean,
  error: string | null,
): { text: string; title: string | undefined } {
  if (chrome === 'unavailable') {
    const base = practice ? PRACTICE_ACCOUNT_UNAVAILABLE : GLOBAL_BAR_ACCOUNT_UNAVAILABLE_TITLE;
    return {
      text: practice ? PRACTICE_ACCOUNT_UNAVAILABLE : GLOBAL_BAR_ACCOUNT_UNAVAILABLE_CHIP,
      title: error ? `${base}: ${error}` : base,
    };
  }
  if (chrome === 'loading') {
    return {
      text: practice ? PRACTICE_ACCOUNT_LOADING : GLOBAL_BAR_ACCOUNT_LOADING_CHIP,
      title: practice ? PRACTICE_ACCOUNT_LOADING : GLOBAL_BAR_ACCOUNT_LOADING_TITLE,
    };
  }
  return { text: GLOBAL_BAR_OFFLINE_CHIP, title: undefined };
}

export function GlobalBarAccountCluster({
  accountChrome,
  accountError,
  summary,
  orders,
  closedOrders,
  traderActive,
  closeTraderView,
  refresh,
  venue = null,
}: Props) {
  const status = useIbkrStatus();
  const practice = usePracticeAccount(venue);
  const [openMenu, setOpenMenu] = useState<ClusterMenu>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const dayCardId = useId();
  const tavCardId = useId();
  const workingMenuId = useId();
  const pillMenuId = useId();

  useEffect(() => {
    if (!openMenu) return;
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpenMenu(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpenMenu(null);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [openMenu]);

  const practiceVenue = isPracticeVenue(venue) ? venue : null;
  const ledger = practiceVenue && practice.data?.venue === practiceVenue ? practice.data : null;
  const chrome: AccountChromeState = practiceVenue
    ? resolvePracticeChromeState({ venue: practiceVenue, data: practice.data, error: practice.error })
    : accountChrome;
  const error = practiceVenue ? practice.error : accountError;
  const figures = ledger ? figuresFromPractice(ledger) : figuresFromSummary(summary);
  const pill = headerAccountPillView({
    venue,
    status,
    summary,
    practiceId: ledger?.account_id ?? null,
  });
  const dayTitle = ledger
    ? practiceDayPnlTitle(
        formatSignedMoney(ledger.realized_pnl),
        formatSignedMoney(ledger.unrealized_pnl),
        ledger.day_started_et,
      )
    : GLOBAL_BAR_DAY_PNL_TITLE;
  const tavTitle = ledger && practiceVenue ? practiceTavTitle(practiceVenue, ledger.account_id) : GLOBAL_BAR_TAV_TITLE;
  const ready = chrome === 'ready';
  const toggle = (menu: ClusterMenu) => () => setOpenMenu((cur) => (cur === menu ? null : menu));
  const hover = (menu: ClusterMenu) => () => setOpenMenu(menu);

  const pillControl = pill && (
    <>
      <span className="global-app-bar__sep" aria-hidden />
      <AccountPillButton
        view={pill}
        open={openMenu === 'pill'}
        menuId={pillMenuId}
        onToggle={toggle('pill')}
        onHover={hover('pill')}
      />
    </>
  );

  return (
    <div
      className="global-app-bar__account"
      ref={wrapRef}
      data-testid="global-bar-account"
      data-venue={venue ?? ''}
      data-source={figures.source}
    >
      {ready ? (
        <div className="global-app-bar__cluster" data-testid="global-bar-cluster">
          <DayPnlButton
            figures={figures}
            open={openMenu === 'day'}
            cardId={dayCardId}
            title={dayTitle}
            onToggle={toggle('day')}
            onHover={hover('day')}
          />
          <span className="global-app-bar__sep" aria-hidden />
          <button
            type="button"
            className="global-app-bar__metric-btn global-app-bar__metric--working"
            aria-expanded={openMenu === 'working'}
            aria-controls={workingMenuId}
            aria-label={GLOBAL_BAR_WORKING_MENU_TITLE}
            data-testid="global-bar-working-trigger"
            onClick={toggle('working')}
            onMouseEnter={hover('working')}
          >
            <label>{GLOBAL_BAR_WORKING_LABEL}</label>
            <span className="global-app-bar__working-count">{orders.length}</span>
            <span className="global-app-bar__caret" aria-hidden>
              {openMenu === 'working' ? '▴' : '▾'}
            </span>
          </button>
          <span className="global-app-bar__sep" aria-hidden />
          <TavButton
            figures={figures}
            open={openMenu === 'tav'}
            cardId={tavCardId}
            title={tavTitle}
            onToggle={toggle('tav')}
            onHover={hover('tav')}
          />
          {pillControl}
        </div>
      ) : (
        <div
          className={`global-app-bar__cluster global-app-bar__cluster--offline${
            chrome === 'loading' ? ' is-loading' : ''
          }`}
          data-testid="global-bar-offline"
          data-chrome={chrome}
          title={offlineChip(chrome, practiceVenue != null, error).title}
        >
          <span className="global-app-bar__offline-chip">
            {offlineChip(chrome, practiceVenue != null, error).text}
          </span>
          <span className="global-app-bar__sep" aria-hidden />
          <span className="global-app-bar__metric global-app-bar__metric--tav">
            <label>{GLOBAL_BAR_TAV_LABEL}</label>
            <span>{GLOBAL_BAR_OFFLINE_PLACEHOLDER}</span>
          </span>
          {pillControl}
        </div>
      )}
      {openMenu === 'day' && ready && (
        <div id={dayCardId}>
          <DayPnlCard figures={figures} />
        </div>
      )}
      {openMenu === 'tav' && ready && (
        <div id={tavCardId}>
          <TavCard figures={figures} />
        </div>
      )}
      {openMenu === 'working' && ready && (
        <div id={workingMenuId}>
          <GlobalWorkingMenu
            workingOrders={orders}
            closedOrders={closedOrders}
            traderActive={traderActive}
            closeTraderView={closeTraderView}
            onRefresh={refresh}
            onClose={() => setOpenMenu(null)}
          />
        </div>
      )}
      {openMenu === 'pill' && pill && (
        <div id={pillMenuId}>
          <AccountPillMenu view={pill} />
        </div>
      )}
    </div>
  );
}
