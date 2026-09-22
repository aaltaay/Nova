/**
 * Shared place helpers for runNovaAction (keeps executor under file-size limit).
 */

import {
  NOVA_ACTION_ACCOUNT_ERROR_MESSAGE,
  NOVA_ACTION_DEPTH_DISABLED_REASON,
} from '../constants';
import {
  beginBrowserExecutionTiming,
  type BrowserActionStamp,
} from '../execution_latency';
import { shouldUseOutsideRth } from '../ibkr/extendedSession';
import { buildLongExitPercent } from '../ibkr/exitPosition';
import { venueClockNow } from '../ibkr/marketOutsideRth';
import { planFlattenExit } from '../ibkr/planFlattenExit';
import { placeIbkrOrder } from '../ibkr/placeOrder';
import type { TopOfBook } from './TopOfBookContext';
import type { NovaActionResult } from './novaActionTypes';
import type { NovaActionRuntime } from './runNovaActionRuntime';

export function accountModeLabel(mode?: string): string {
  const m = (mode || '').toLowerCase();
  if (m === 'live') return 'LIVE';
  if (m === 'paper') return 'PAPER';
  return (mode || 'unknown').toUpperCase();
}

export function requireDepth(
  runtime: NovaActionRuntime,
  symbol: string,
): TopOfBook | NovaActionResult {
  const tob = runtime.topOfBook;
  if (
    !tob
    || tob.symbol.toUpperCase() !== symbol
    || !tob.depthSubscribed
  ) {
    return { ok: false, text: NOVA_ACTION_DEPTH_DISABLED_REASON };
  }
  return tob;
}

export async function placeMarketExit(
  runtime: NovaActionRuntime,
  symbol: string,
  side: 'BUY' | 'SELL',
  qty: number,
  label: string,
  actionTiming: BrowserActionStamp,
  maybeConfirm: (runtime: NovaActionRuntime, summary: string) => Promise<boolean>,
  idempotencyKey?: string,
  /**
   * `'flatten'` for a whole-position close (QA R32): the server checks it
   * closes the held shares not already being closed and sends it as the
   * protective flatten, never clamped to 1 share. Partial exits omit it.
   */
  intent?: 'flatten',
): Promise<NovaActionResult> {
  const ticket = planFlattenExit(side, {
    book: {
      bid: runtime.topOfBook?.bid,
      ask: runtime.topOfBook?.ask,
      last: runtime.position?.market_price,
    },
    // Regular hours by the venue's clock: the Sim playhead on Sim (QA R21).
    now: venueClockNow(runtime.accountMode),
  });
  if (!ticket.ok) {
    return { ok: false, text: ticket.error };
  }
  const hours = ticket.outside_rth ? ' extended hours' : '';
  const mode = accountModeLabel(runtime.accountMode);
  const kind = ticket.order_type === 'LMT'
    ? `LMT ${ticket.limit_price}`
    : 'MKT';
  const summary =
    `${side} ${qty} ${symbol} (${kind}${hours} ${label}) on ${mode} account.`;
  if (!(await maybeConfirm(runtime, summary))) {
    return { ok: false, text: 'Order cancelled' };
  }
  try {
    const res = await placeIbkrOrder(
      {
        symbol,
        side,
        qty,
        order_type: ticket.order_type,
        outside_rth: ticket.outside_rth,
        limit_price: ticket.limit_price,
        ...(intent ? { intent } : {}),
      },
      idempotencyKey,
      {
        timing: beginBrowserExecutionTiming('nova_action_place', actionTiming),
      },
    );
    return {
      ok: res.ok,
      text: res.ok
        ? `Exit order #${res.order_id}${ticket.outside_rth ? ' (EH)' : ''}`
        : res.error ?? 'Exit failed',
      ...(!res.ok
        ? {
            reasonCode: res.reason_code,
            order: { symbol, side, qty, mode },
          }
        : {}),
    };
  } catch {
    return { ok: false, text: 'Network error placing exit' };
  }
}

export async function placeLongPctLimit(
  runtime: NovaActionRuntime,
  symbol: string,
  percent: number,
  priceBase: 'ask' | 'bid',
  offsetDollars: number,
  actionTiming: BrowserActionStamp,
  maybeConfirm: (runtime: NovaActionRuntime, summary: string) => Promise<boolean>,
  idempotencyKey?: string,
): Promise<NovaActionResult> {
  if (runtime.accountError) {
    return { ok: false, text: NOVA_ACTION_ACCOUNT_ERROR_MESSAGE };
  }
  const built = buildLongExitPercent(runtime.position?.qty, percent);
  if (!built.ok) return { ok: false, text: built.error };

  const tobOrErr = requireDepth(runtime, symbol);
  if ('ok' in tobOrErr && tobOrErr.ok === false) return tobOrErr;
  const tob = tobOrErr as TopOfBook;

  const base = priceBase === 'ask' ? tob.ask : tob.bid;
  if (base == null || base <= 0) {
    return { ok: false, text: NOVA_ACTION_DEPTH_DISABLED_REASON };
  }
  const limit = priceBase === 'ask' ? base + offsetDollars : base - offsetDollars;
  if (limit <= 0) {
    return { ok: false, text: 'Computed limit price is invalid' };
  }

  const outside_rth = shouldUseOutsideRth(false);
  const mode = accountModeLabel(runtime.accountMode);
  const ref = priceBase === 'ask' ? 'ASK' : 'BID';
  const off =
    offsetDollars === 0
      ? ''
      : priceBase === 'ask'
        ? ` +$${offsetDollars.toFixed(2)}`
        : ` -$${offsetDollars.toFixed(2)}`;
  const summary =
    `SELL ${built.qty} ${symbol} (${percent}% long) LMT @ $${limit.toFixed(2)} `
    + `(${ref}${off}) on ${mode} account.`;
  if (!(await maybeConfirm(runtime, summary))) {
    return { ok: false, text: 'Order cancelled' };
  }

  try {
    const res = await placeIbkrOrder(
      {
        symbol,
        side: 'SELL',
        qty: built.qty,
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
            order: { symbol, side: 'SELL', qty: built.qty, mode },
          }
        : {}),
    };
  } catch {
    return { ok: false, text: 'Network error placing order' };
  }
}
