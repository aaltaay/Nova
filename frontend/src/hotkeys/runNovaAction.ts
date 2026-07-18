/**
 * Execute a typed Nova Action via the manual order path (System 2).
 */

import {
  NOVA_ACTION_DEPTH_DISABLED_REASON,
  NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_SHARES,
  NOVA_ACTION_NO_SYMBOL_MESSAGE,
  NOVA_ACTION_PIN_LOCKED_MESSAGE,
  NOVA_ACTION_SPEND_LOCKED_MESSAGE,
} from '../constants';
import { buildExitFullPosition, buildExitPositionPercent } from '../ibkr/exitPosition';
import {
  cancelAllOrdersForSymbol,
  placeIbkrOrder,
} from '../ibkr/placeOrder';
import { readSkipPlaceConfirm } from '../ibkr/placeConfirmPrefs';
import { readTicketSessionUnlocked } from '../ibkr/ticketUnlock';
import type { IbkrPosition } from '../ibkr/types';
import type { TopOfBook } from './TopOfBookContext';
import type { NovaActionRecord, NovaActionResult } from './novaActionTypes';

export interface NovaActionRuntime {
  symbol: string | null;
  connected: boolean;
  spendStatus?: string;
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
  return window.confirm(summary);
}

export async function runNovaAction(
  action: NovaActionRecord,
  runtime: NovaActionRuntime,
): Promise<NovaActionResult> {
  const gated = gateManual(runtime);
  if (gated) return gated;

  const symbol = runtime.symbol!.toUpperCase();

  if (action.kind === 'cancel_symbol') {
    try {
      const res = await cancelAllOrdersForSymbol(symbol);
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

  if (action.kind === 'exit_pos' || action.kind === 'exit_pos_pct') {
    const built = action.kind === 'exit_pos'
      ? buildExitFullPosition(runtime.position?.qty)
      : buildExitPositionPercent(runtime.position?.qty, action.params.percent ?? 50);
    if (!built.ok) return { ok: false, text: built.error };

    const summary =
      `${built.side} ${built.qty} ${symbol} (MKT exit) on the connected account.`;
    if (!(await maybeConfirm(runtime, summary))) {
      return { ok: false, text: 'Order cancelled' };
    }
    try {
      const res = await placeIbkrOrder({
        symbol,
        side: built.side,
        qty: built.qty,
        order_type: 'MKT',
        outside_rth: false,
      });
      return {
        ok: res.ok,
        text: res.ok
          ? `Exit order #${res.order_id}`
          : res.error ?? 'Exit failed',
      };
    } catch {
      return { ok: false, text: 'Network error placing exit' };
    }
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
    const summary =
      `${side} ${shares} ${symbol} (LMT @ $${limit.toFixed(2)})`;
    if (!(await maybeConfirm(runtime, summary))) {
      return { ok: false, text: 'Order cancelled' };
    }
    try {
      const res = await placeIbkrOrder({
        symbol,
        side,
        qty: shares,
        order_type: 'LMT',
        limit_price: Number(limit.toFixed(4)),
        outside_rth: false,
      });
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
