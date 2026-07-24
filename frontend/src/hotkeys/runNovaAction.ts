/**
 * Execute a typed Nova Action via the manual order path (System 2).
 */

import {
  NOVA_ACTION_ACCOUNT_ERROR_MESSAGE,
  NOVA_ACTION_DEPTH_DISABLED_REASON,
  NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_SHARES,
  NOVA_ACTION_NO_SYMBOL_MESSAGE,
  NOVA_ACTION_PIN_LOCKED_MESSAGE,
  NOVA_ACTION_SPEND_LOCKED_MESSAGE,
} from '../constants';
import {
  beginBrowserExecutionTiming,
  captureBrowserAction,
  type BrowserActionStamp,
} from '../execution_latency';
import { shouldUseOutsideRth } from '../ibkr/extendedSession';
import { buildExitFullPosition, buildExitPositionPercent } from '../ibkr/exitPosition';
import {
  cancelAllOrdersForSymbol,
  placeIbkrOrder,
} from '../ibkr/placeOrder';
import { readSkipPlaceConfirm } from '../ibkr/placeConfirmPrefs';
import { readTicketSessionUnlocked } from '../ibkr/ticketUnlock';
import type { IbkrPosition } from '../ibkr/types';
import { confirmApp } from '../ux';
import type { TopOfBook } from './TopOfBookContext';
import type { NovaActionRecord, NovaActionResult } from './novaActionTypes';

export interface NovaActionRuntime {
  symbol: string | null;
  connected: boolean;
  spendStatus?: string;
  /** Set when useIbkrAccount last poll failed — block exit/flatten actions. */
  accountError?: string | null;
  position: IbkrPosition | null;
  topOfBook: TopOfBook | null;
  /** Called when place-confirm is required; return true to proceed. */
  requestConfirm?: (summary: string) => Promise<boolean>;
}

function spendLocked(status?: string): boolean {
  return status === 'locked' || status === 'locked_live_unconfirmed';
}

function gateManual(runtime: NovaActionRuntime): NovaActionResult | null {
  if (!runtime.symbol) {
    return { ok: false, text: NOVA_ACTION_NO_SYMBOL_MESSAGE };
  }
  if (!runtime.connected) {
    return { ok: false, text: 'IBKR disconnected — connect Gateway first' };
  }
  if (!readTicketSessionUnlocked()) {
    return { ok: false, text: NOVA_ACTION_PIN_LOCKED_MESSAGE };
  }
  if (spendLocked(runtime.spendStatus)) {
    return { ok: false, text: NOVA_ACTION_SPEND_LOCKED_MESSAGE };
  }
  return null;
}

async function maybeConfirm(
  runtime: NovaActionRuntime,
  summary: string,
): Promise<boolean> {
  if (readSkipPlaceConfirm()) return true;
  if (runtime.requestConfirm) return runtime.requestConfirm(summary);
  return confirmApp({
    title: 'Confirm Nova Action',
    message: summary,
    confirmLabel: 'Place',
    tone: 'warning',
  });
}

async function placeMarketExit(
  runtime: NovaActionRuntime,
  symbol: string,
  side: 'BUY' | 'SELL',
  qty: number,
  label: string,
  actionTiming: BrowserActionStamp,
): Promise<NovaActionResult> {
  const outside_rth = shouldUseOutsideRth(false);
  const hours = outside_rth ? ' extended hours' : '';
  const summary = `${side} ${qty} ${symbol} (MKT${hours} ${label}) on the connected account.`;
  if (!(await maybeConfirm(runtime, summary))) {
    return { ok: false, text: 'Order cancelled' };
  }
  try {
    const res = await placeIbkrOrder(
      {
        symbol,
        side,
        qty,
        order_type: 'MKT',
        outside_rth,
      },
      undefined,
      {
        timing: beginBrowserExecutionTiming('nova_action_place', actionTiming),
      },
    );
    return {
      ok: res.ok,
      text: res.ok
        ? `Exit order #${res.order_id}${outside_rth ? ' (EH)' : ''}`
        : res.error ?? 'Exit failed',
    };
  } catch {
    return { ok: false, text: 'Network error placing exit' };
  }
}

export async function runNovaAction(
  action: NovaActionRecord,
  runtime: NovaActionRuntime,
): Promise<NovaActionResult> {
  const actionTiming = captureBrowserAction('user_action');
  const gated = gateManual(runtime);
  if (gated) return gated;

  const symbol = runtime.symbol!.toUpperCase();

  if (action.kind === 'cancel_symbol') {
    try {
      const res = await cancelAllOrdersForSymbol(
        symbol,
        beginBrowserExecutionTiming('nova_action_cancel', actionTiming),
      );
      if (res.ok) {
        const n = res.cancelled.length;
        return {
          ok: true,
          text: n === 0
            ? `No open orders for ${symbol}`
            : `Cancelled ${n} order(s) for ${symbol}`,
        };
      }
      return { ok: false, text: res.error ?? 'Cancel-all failed' };
    } catch {
      return { ok: false, text: 'Network error cancelling orders' };
    }
  }

  if (action.kind === 'cancel_and_exit') {
    if (runtime.accountError) {
      return { ok: false, text: NOVA_ACTION_ACCOUNT_ERROR_MESSAGE };
    }
    let cancelText = '';
    try {
      const res = await cancelAllOrdersForSymbol(
        symbol,
        beginBrowserExecutionTiming('nova_action_cancel', actionTiming),
      );
      if (!res.ok) {
        return { ok: false, text: res.error ?? 'Cancel-all failed before flatten' };
      }
      const n = res.cancelled.length;
      cancelText = n === 0 ? 'No open orders' : `Cancelled ${n}`;
    } catch {
      return { ok: false, text: 'Network error cancelling orders before flatten' };
    }

    const built = buildExitFullPosition(runtime.position?.qty);
    if (!built.ok) {
      return {
        ok: true,
        text: `${cancelText} for ${symbol}. ${built.error}`,
      };
    }
    const exit = await placeMarketExit(
      runtime,
      symbol,
      built.side,
      built.qty,
      'cancel+flatten',
      actionTiming,
    );
    if (!exit.ok) {
      return {
        ok: false,
        text: `${cancelText} for ${symbol}. Flatten: ${exit.text}`,
      };
    }
    return {
      ok: true,
      text: `${cancelText} for ${symbol}. ${exit.text}`,
    };
  }

  if (action.kind === 'exit_pos' || action.kind === 'exit_pos_pct') {
    if (runtime.accountError) {
      return { ok: false, text: NOVA_ACTION_ACCOUNT_ERROR_MESSAGE };
    }
    const built = action.kind === 'exit_pos'
      ? buildExitFullPosition(runtime.position?.qty)
      : buildExitPositionPercent(runtime.position?.qty, action.params.percent ?? 50);
    if (!built.ok) return { ok: false, text: built.error };

    return placeMarketExit(
      runtime,
      symbol,
      built.side,
      built.qty,
      action.kind === 'exit_pos' ? 'flatten' : 'partial exit',
      actionTiming,
    );
  }

  if (action.kind === 'buy_limit_ask_offset' || action.kind === 'sell_limit_bid_offset') {
    const tob = runtime.topOfBook;
    if (
      !tob
      || tob.symbol.toUpperCase() !== symbol
      || !tob.depthSubscribed
    ) {
      return { ok: false, text: NOVA_ACTION_DEPTH_DISABLED_REASON };
    }
    const offset = action.params.offsetDollars ?? NOVA_ACTION_DEFAULT_OFFSET_DOLLARS;
    const shares = action.params.shares ?? NOVA_ACTION_DEFAULT_SHARES;
    const isBuy = action.kind === 'buy_limit_ask_offset';
    const base = isBuy ? tob.ask : tob.bid;
    if (base == null || base <= 0) {
      return { ok: false, text: NOVA_ACTION_DEPTH_DISABLED_REASON };
    }
    const limit = isBuy ? base + offset : base - offset;
    if (limit <= 0) {
      return { ok: false, text: 'Computed limit price is invalid' };
    }
    const side = isBuy ? 'BUY' : 'SELL';
    const outside_rth = shouldUseOutsideRth(false);
    const summary =
      `${side} ${shares} ${symbol} (LMT @ $${limit.toFixed(2)}${outside_rth ? ' EH' : ''})`;
    if (!(await maybeConfirm(runtime, summary))) {
      return { ok: false, text: 'Order cancelled' };
    }
    try {
      const res = await placeIbkrOrder(
        {
          symbol,
          side,
          qty: shares,
          order_type: 'LMT',
          limit_price: Number(limit.toFixed(4)),
          outside_rth,
        },
        undefined,
        {
          timing: beginBrowserExecutionTiming('nova_action_place', actionTiming),
          referencePrice: base,
        },
      );
      return {
        ok: res.ok,
        text: res.ok
          ? `Order #${res.order_id} placed`
          : res.error ?? 'Order failed',
      };
    } catch {
      return { ok: false, text: 'Network error placing order' };
    }
  }

  return { ok: false, text: 'Unknown Nova Action' };
}
