/**
 * Execute a typed Nova Action via the manual order path (System 2).
 * Paper and live share this path; spend/Gateway gates differ by environment.
 */

import {
  NOVA_ACTION_ACCOUNT_ERROR_MESSAGE,
  NOVA_ACTION_DEPTH_DISABLED_REASON,
  NOVA_ACTION_DEFAULT_BID_EXIT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_BUY_MARKET_SHARES,
  NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_SHARES,
  NOVA_ACTION_NO_SYMBOL_MESSAGE,
  NOVA_ACTION_SPEND_LOCKED_MESSAGE,
} from '../constants';
import {
  beginBrowserExecutionTiming,
  captureBrowserAction,
} from '../execution_latency';
import { shouldUseOutsideRth } from '../ibkr/extendedSession';
import {
  buildBuyMarketShares,
  buildExitFullPosition,
  buildExitPositionPercent,
} from '../ibkr/exitPosition';
import { newGestureKey } from '../ibkr/gestureKey';
import {
  cancelAllOrdersForSymbol,
  cancelAllWorkingOrders,
  countOpenWorkingOrders,
  placeIbkrOrder,
} from '../ibkr/placeOrder';
import { readSkipPlaceConfirm } from '../ibkr/placeConfirmPrefs';
import { readTicketSessionUnlocked } from '../ibkr/ticketUnlock';
import { evaluateTradingAllowed } from '../ibkr/tradingAllowed';
import { confirmApp } from '../ux';
import type { TopOfBook } from './TopOfBookContext';
import type { NovaActionRecord, NovaActionResult } from './novaActionTypes';
import {
  accountModeLabel,
  placeLongPctLimit,
  placeMarketExit,
  requireDepth,
} from './runNovaActionPlace';
import type { NovaActionRuntime } from './runNovaActionRuntime';

export type { NovaActionRuntime } from './runNovaActionRuntime';

function gateConnected(runtime: NovaActionRuntime): NovaActionResult | null {
  const gate = evaluateTradingAllowed({
    connected: runtime.connected,
    spendStatus: runtime.spendStatus,
    sessionUnlocked: readTicketSessionUnlocked(),
  });
  if (!gate.allowed) {
    return { ok: false, text: gate.reason ?? NOVA_ACTION_SPEND_LOCKED_MESSAGE };
  }
  return null;
}

function gateManual(runtime: NovaActionRuntime): NovaActionResult | null {
  if (!runtime.symbol) {
    return { ok: false, text: NOVA_ACTION_NO_SYMBOL_MESSAGE };
  }
  return gateConnected(runtime);
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
    skipConfirmOption: true,
  });
}

export async function runNovaAction(
  action: NovaActionRecord,
  runtime: NovaActionRuntime,
): Promise<NovaActionResult> {
  const actionTiming = captureBrowserAction('user_action');
  // One keypress is one gesture: every place this invocation makes carries
  // the same key, so a re-fired hotkey replays instead of doubling up.
  const idempotencyKey = newGestureKey(`nova_action:${action.kind}`);

  if (action.kind === 'cancel_all_orders') {
    const gated = gateConnected(runtime);
    if (gated) return gated;
    const mode = accountModeLabel(runtime.accountMode);
    const openCount = await countOpenWorkingOrders();
    const countPart =
      openCount == null
        ? 'all working orders'
        : `${openCount} working order(s)`;
    const summary =
      `Cancel ${countPart} on the connected ${mode} account (all symbols).`;
    if (!(await maybeConfirm(runtime, summary))) {
      return { ok: false, text: 'Cancel cancelled' };
    }
    try {
      const res = await cancelAllWorkingOrders(
        beginBrowserExecutionTiming('nova_action_cancel', actionTiming),
      );
      if (!res.ok && res.cancelled.length === 0) {
        return { ok: false, text: res.error ?? 'Cancel-all failed' };
      }
      const n = res.cancelled.length;
      const failN = res.failed.length;
      if (failN > 0) {
        return {
          ok: false,
          text:
            `Cancelled ${n}; ${failN} failed`
            + (res.error ? ` (${res.error})` : ''),
        };
      }
      return {
        ok: true,
        text: n === 0
          ? 'No open orders to cancel'
          : `Cancelled ${n} order(s) (all symbols)`,
      };
    } catch {
      return { ok: false, text: 'Network error cancelling orders' };
    }
  }

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
      maybeConfirm,
      idempotencyKey,
      'flatten',
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
      maybeConfirm,
      idempotencyKey,
      action.kind === 'exit_pos' ? 'flatten' : undefined,
    );
  }

  if (action.kind === 'buy_market') {
    const shares = action.params.shares ?? NOVA_ACTION_DEFAULT_BUY_MARKET_SHARES;
    const built = buildBuyMarketShares(shares);
    if (!built.ok) return { ok: false, text: built.error };
    const outside_rth = shouldUseOutsideRth(false);
    const mode = accountModeLabel(runtime.accountMode);
    const summary =
      `BUY ${built.qty} ${symbol} (MKT${outside_rth ? ' EH' : ''}) on ${mode} account.`;
    if (!(await maybeConfirm(runtime, summary))) {
      return { ok: false, text: 'Order cancelled' };
    }
    try {
      const res = await placeIbkrOrder(
        {
          symbol,
          side: 'BUY',
          qty: built.qty,
          order_type: 'MKT',
          outside_rth,
        },
        idempotencyKey,
        {
          timing: beginBrowserExecutionTiming('nova_action_place', actionTiming),
        },
      );
      return {
        ok: res.ok,
        text: res.ok
          ? `Order #${res.order_id} placed`
          : res.error ?? 'Order failed',
        ...(!res.ok
          ? {
              reasonCode: res.reason_code,
              order: { symbol, side: 'BUY', qty: built.qty, mode },
            }
          : {}),
      };
    } catch {
      return { ok: false, text: 'Network error placing order' };
    }
  }

  if (action.kind === 'sell_pos_pct_ask') {
    return placeLongPctLimit(
      runtime,
      symbol,
      action.params.percent ?? 50,
      'ask',
      action.params.offsetDollars ?? 0,
      actionTiming,
      maybeConfirm,
      idempotencyKey,
    );
  }

  if (action.kind === 'sell_pos_pct_bid_offset') {
    return placeLongPctLimit(
      runtime,
      symbol,
      action.params.percent ?? 50,
      'bid',
      action.params.offsetDollars ?? NOVA_ACTION_DEFAULT_BID_EXIT_OFFSET_DOLLARS,
      actionTiming,
      maybeConfirm,
      idempotencyKey,
    );
  }

  if (
    action.kind === 'buy_limit_ask_offset'
    || action.kind === 'sell_limit_bid_offset'
    || action.kind === 'sell_limit_ask_offset'
  ) {
    const tobOrErr = requireDepth(runtime, symbol);
    if ('ok' in tobOrErr && tobOrErr.ok === false) return tobOrErr;
    const tob = tobOrErr as TopOfBook;
    const offset = action.params.offsetDollars ?? NOVA_ACTION_DEFAULT_OFFSET_DOLLARS;
    const shares = action.params.shares ?? NOVA_ACTION_DEFAULT_SHARES;
    const isBuy = action.kind === 'buy_limit_ask_offset';
    const fromAsk = action.kind !== 'sell_limit_bid_offset';
    const base = fromAsk ? tob.ask : tob.bid;
    if (base == null || base <= 0) {
      return { ok: false, text: NOVA_ACTION_DEPTH_DISABLED_REASON };
    }
    const limit = fromAsk ? base + offset : base - offset;
    if (limit <= 0) {
      return { ok: false, text: 'Computed limit price is invalid' };
    }
    const side = isBuy ? 'BUY' : 'SELL';
    const outside_rth = shouldUseOutsideRth(Boolean(action.params.outsideRth));
    const mode = accountModeLabel(runtime.accountMode);
    const summary =
      `${side} ${shares} ${symbol} (LMT @ $${limit.toFixed(2)}${outside_rth ? ' EH' : ''}) `
      + `on ${mode} account.`;
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
        idempotencyKey,
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
        ...(!res.ok
          ? {
              reasonCode: res.reason_code,
              order: { symbol, side, qty: shares, mode },
            }
          : {}),
      };
    } catch {
      return { ok: false, text: 'Network error placing order' };
    }
  }

  return { ok: false, text: 'Unknown Nova Action' };
}
