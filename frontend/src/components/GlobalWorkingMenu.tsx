/**
 * Webull-style Working dropdown — status counts + cancel / view actions.
 */
import { useState } from 'react';
import {
  GLOBAL_BAR_CANCEL_ALL_BUSY_WHY,
  GLOBAL_BAR_CANCEL_ALL_CONFIRM_BODY,
  GLOBAL_BAR_CANCEL_ALL_CONFIRM_LABEL,
  GLOBAL_BAR_CANCEL_ALL_CONFIRM_TITLE,
  GLOBAL_BAR_CANCEL_ALL_EMPTY_TITLE,
  GLOBAL_BAR_CANCEL_ALL_STOCKS,
  GLOBAL_BAR_CANCELED_FAILED_LABEL,
  GLOBAL_BAR_FILLED_TODAY_LABEL,
  GLOBAL_BAR_VIEW_ALL_ORDERS,
  GLOBAL_BAR_WORKING_COUNT_WHY,
  GLOBAL_BAR_WORKING_MENU_TITLE,
  GLOBAL_BAR_WORKING_ORDERS_LABEL,
} from '../constants';
import { cancelAllOrdersForSymbol } from '../ibkr/placeOrder';
import type { IbkrOrder } from '../ibkr/types';
import { confirmApp, alertApp } from '../ux';
import { globalWorkingCounts, workingOrderSymbols } from './globalWorkingCounts';
import type { ClosedOrder } from '../closed_orders/types';
import { requestOpenTradingTab } from './openTradingTabNav';

interface Props {
  workingOrders: IbkrOrder[];
  closedOrders: ClosedOrder[];
  traderActive: boolean;
  closeTraderView: () => void;
  onRefresh: () => void;
  onClose: () => void;
}

export function GlobalWorkingMenu({
  workingOrders,
  closedOrders,
  traderActive,
  closeTraderView,
  onRefresh,
  onClose,
}: Props) {
  const counts = globalWorkingCounts(workingOrders, closedOrders);
  const [busy, setBusy] = useState(false);
  // A locked Cancel All says why (ux/whyTip.ts).
  const cancelAllWhy = busy
    ? GLOBAL_BAR_CANCEL_ALL_BUSY_WHY
    : counts.working === 0
      ? GLOBAL_BAR_CANCEL_ALL_EMPTY_TITLE
      : undefined;

  async function handleCancelAllStocks() {
    const symbols = workingOrderSymbols(workingOrders);
    if (symbols.length === 0) {
      await alertApp({
        title: GLOBAL_BAR_CANCEL_ALL_EMPTY_TITLE,
        message: GLOBAL_BAR_CANCEL_ALL_EMPTY_TITLE,
      });
      return;
    }
    const ok = await confirmApp({
      title: GLOBAL_BAR_CANCEL_ALL_CONFIRM_TITLE,
      message: GLOBAL_BAR_CANCEL_ALL_CONFIRM_BODY,
      confirmLabel: GLOBAL_BAR_CANCEL_ALL_CONFIRM_LABEL,
    });
    if (!ok) return;
    setBusy(true);
    try {
      for (const sym of symbols) {
        await cancelAllOrdersForSymbol(sym);
      }
      onRefresh();
    } finally {
      setBusy(false);
      onClose();
    }
  }

  function handleViewAllOrders() {
    onClose();
    // Latch first so DashboardPage consumes it after Trader unmounts.
    requestOpenTradingTab();
    if (traderActive) closeTraderView();
  }

  return (
    <div
      className="global-app-bar__card global-app-bar__working-menu"
      role="menu"
      aria-label={GLOBAL_BAR_WORKING_MENU_TITLE}
      data-testid="global-working-menu"
    >
      <div className="global-app-bar__card-row" role="menuitem" aria-disabled data-why={GLOBAL_BAR_WORKING_COUNT_WHY}>
        <span>{GLOBAL_BAR_WORKING_ORDERS_LABEL}</span>
        <span className="global-app-bar__working-count">{counts.working}</span>
      </div>
      <div className="global-app-bar__card-row" role="menuitem" aria-disabled data-why={GLOBAL_BAR_WORKING_COUNT_WHY}>
        <span>{GLOBAL_BAR_FILLED_TODAY_LABEL}</span>
        <span className="global-app-bar__tone--filled">{counts.filledToday}</span>
      </div>
      <div className="global-app-bar__card-row" role="menuitem" aria-disabled data-why={GLOBAL_BAR_WORKING_COUNT_WHY}>
        <span>{GLOBAL_BAR_CANCELED_FAILED_LABEL}</span>
        <span className="global-app-bar__tone--down">{counts.canceledFailed}</span>
      </div>

      <div className="global-app-bar__menu-divider" aria-hidden />

      <button
        type="button"
        className="global-app-bar__menu-action"
        role="menuitem"
        disabled={busy || counts.working === 0}
        data-why={cancelAllWhy}
        data-testid="global-working-cancel-all"
        onClick={() => {
          void handleCancelAllStocks();
        }}
      >
        {GLOBAL_BAR_CANCEL_ALL_STOCKS}
      </button>
      <button
        type="button"
        className="global-app-bar__menu-action"
        role="menuitem"
        data-testid="global-working-view-all"
        onClick={handleViewAllOrders}
      >
        {GLOBAL_BAR_VIEW_ALL_ORDERS}
      </button>
    </div>
  );
}
