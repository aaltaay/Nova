/**
 * Net Liq / Day P&L / Working cluster for GlobalAppBar.
 * Separate from GATEWAY market-data chip -- never label "IBKR offline" while Gateway is up.
 */
import type { Dispatch, SetStateAction } from 'react';
import type { IbkrAccountSummary, IbkrOrder } from '../ibkr/types';
import {
  GLOBAL_BAR_ACCOUNT_LOADING_CHIP,
  GLOBAL_BAR_ACCOUNT_UNAVAILABLE_CHIP,
  GLOBAL_BAR_DAY_PNL_LABEL,
  GLOBAL_BAR_NET_LIQ_LABEL,
  GLOBAL_BAR_OFFLINE_CHIP,
  GLOBAL_BAR_OFFLINE_PLACEHOLDER,
  GLOBAL_BAR_WORKING_LABEL,
  GLOBAL_BAR_WORKING_MENU_TITLE,
} from '../constants';
import { formatMoney } from '../utils/formatMoney';
import type { AccountChromeState } from './globalBarAccountChrome';
import { GlobalAccountCard } from './GlobalAccountCard';
import { GlobalWorkingMenu } from './GlobalWorkingMenu';
import { dayPnlFromSummary, formatSignedMoney, pnlToneClass } from './globalBarMoney';

type OpenMenu = 'account' | 'working' | null;

export function GlobalBarAccountCluster({
  accountChrome,
  accountError,
  summary,
  orders,
  workingCount,
  openMenu,
  setOpenMenu,
  accountCardId,
  workingMenuId,
  closedOrders,
  traderActive,
  closeTraderView,
  refresh,
}: {
  accountChrome: AccountChromeState;
  accountError: string | null;
  summary: IbkrAccountSummary | null;
  orders: IbkrOrder[];
  workingCount: number;
  openMenu: OpenMenu;
  setOpenMenu: Dispatch<SetStateAction<OpenMenu>>;
  accountCardId: string;
  workingMenuId: string;
  closedOrders: IbkrOrder[];
  traderActive: boolean;
  closeTraderView: () => void;
  refresh: () => void;
}) {
  const live = accountChrome === 'ready';
  const dayPnl = dayPnlFromSummary(summary?.RealizedPnL, summary?.UnrealizedPnL);

  return (
    <>
      {live ? (
        <div className="global-app-bar__cluster" data-testid="global-bar-cluster">
          <button
            type="button"
            className="global-app-bar__metric-btn global-app-bar__metric--day"
            aria-expanded={openMenu === 'account'}
            aria-controls={accountCardId}
            data-testid="global-bar-account-trigger"
            onClick={() => setOpenMenu(m => (m === 'account' ? null : 'account'))}
            onMouseEnter={() => setOpenMenu('account')}
          >
            <label>{GLOBAL_BAR_DAY_PNL_LABEL}</label>
            <span className={pnlToneClass(dayPnl)}>{formatSignedMoney(dayPnl)}</span>
          </button>
          <span className="global-app-bar__sep" aria-hidden />
          <button
            type="button"
            className="global-app-bar__metric-btn global-app-bar__metric--netliq"
            aria-expanded={openMenu === 'account'}
            onClick={() => setOpenMenu(m => (m === 'account' ? null : 'account'))}
            onMouseEnter={() => setOpenMenu('account')}
          >
            <label>{GLOBAL_BAR_NET_LIQ_LABEL}</label>
            <span>{formatMoney(summary?.NetLiquidation)}</span>
          </button>
          <span className="global-app-bar__sep" aria-hidden />
          <button
            type="button"
            className="global-app-bar__metric-btn global-app-bar__metric--working"
            aria-expanded={openMenu === 'working'}
            aria-controls={workingMenuId}
            aria-label={GLOBAL_BAR_WORKING_MENU_TITLE}
            data-testid="global-bar-working-trigger"
            onClick={() => setOpenMenu(m => (m === 'working' ? null : 'working'))}
            onMouseEnter={() => setOpenMenu('working')}
          >
            <label>{GLOBAL_BAR_WORKING_LABEL}</label>
            <span className="global-app-bar__working-count">{workingCount}</span>
            <span className="global-app-bar__caret" aria-hidden>
              {openMenu === 'working' ? '▴' : '▾'}
            </span>
          </button>
        </div>
      ) : (
        <div
          className={`global-app-bar__cluster global-app-bar__cluster--offline${
            accountChrome === 'loading' ? ' is-loading' : ''
          }`}
          data-testid="global-bar-offline"
          data-chrome={accountChrome}
          title={
            accountChrome === 'unavailable'
              ? (accountError || 'Account snapshot unavailable')
              : accountChrome === 'loading'
                ? 'Gateway connected -- loading account snapshot'
                : undefined
          }
        >
          <span className="global-app-bar__offline-chip">
            {accountChrome === 'unavailable'
              ? GLOBAL_BAR_ACCOUNT_UNAVAILABLE_CHIP
              : accountChrome === 'loading'
                ? GLOBAL_BAR_ACCOUNT_LOADING_CHIP
                : GLOBAL_BAR_OFFLINE_CHIP}
          </span>
          <span className="global-app-bar__sep" aria-hidden />
          <span className="global-app-bar__metric">
            <label>{GLOBAL_BAR_NET_LIQ_LABEL}</label>
            <span>{GLOBAL_BAR_OFFLINE_PLACEHOLDER}</span>
          </span>
        </div>
      )}
      {openMenu === 'account' && live && (
        <div id={accountCardId}>
          <GlobalAccountCard summary={summary} />
        </div>
      )}
      {openMenu === 'working' && live && (
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
    </>
  );
}
