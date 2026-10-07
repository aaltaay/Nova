/**
 * The Short and Cover hotkeys (ADR 048, #778 step 3), off runNovaAction.
 *
 * - A Short is a Limit priced from the book -- the bid or the ask plus its signed offset; a short under SSR may
 *   execute only above the bid, so the default is a cent over it -- and always goes out with its buy stop: the
 *   hotkey's own offset over the limit, else the venue's Settings > Trade offset. It is an ordinary manual order:
 *   the opening-order gate, ADR 045's view lock, and the one short check at the door. Regular hours only: no
 *   short opens outside 09:35-15:50.
 * - A Cover buys the whole short back: at the ask plus its offset (a limit), or all of it through the protective
 *   flatten (`cover_pos`, like Flatten: never past flat, and the door checks it).
 * - Nova never flips: a Short while you are long, or a Cover with no short, is refused here before anything is
 *   sent (the door refuses both too).
 */
import {
  NOVA_ACTION_ACCOUNT_ERROR_MESSAGE,
  NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_SHARES,
  NOVA_ACTION_DEFAULT_SHORT_OFFSET_DOLLARS,
  NOVA_ACTION_DEPTH_DISABLED_REASON,
  type NovaActionKind,
} from '../constants';
import { SHORT_HOTKEY_NO_SHORT, SHORT_WHY_LONG } from '../constantGroups/short_ticket';
import { beginBrowserExecutionTiming, type BrowserActionStamp } from '../execution_latency';
import { getConfirmedDeskVenueSnapshot, placeIbkrOrder } from '../ibkr';
import { readTradeDefaultsPrefs } from '../settings';
import type { NovaActionRecord, NovaActionResult } from './novaActionTypes';
import { accountModeLabel, placeMarketExit, requireDepth } from './runNovaActionPlace';
import type { NovaActionRuntime } from './runNovaActionRuntime';
import type { TopOfBook } from './TopOfBookContext';

export const SHORT_HOTKEY_KINDS: ReadonlySet<NovaActionKind> = new Set<NovaActionKind>([
  'short_limit_bid_offset',
  'short_limit_ask_offset',
  'cover_limit_ask_offset',
  'cover_pos',
]);

type Confirm = (runtime: NovaActionRuntime, summary: string) => Promise<boolean>;

const cents = (px: number): number => Math.round(px * 100) / 100;

/** The buy stop's offset over the limit: the hotkey's own, else the desk venue's Settings > Trade default. */
export function shortStopOffset(action: NovaActionRecord): number {
  const own = action.params.stopOffsetDollars;
  if (own != null && Number.isFinite(own) && own > 0) return own;
  return readTradeDefaultsPrefs(getConfirmedDeskVenueSnapshot().venue).shortStopOffset;
}

/** The short a Short hotkey sends from this book: its limit and buy stop, or why it cannot. */
export function planShortHotkey(
  action: NovaActionRecord,
  book: Pick<TopOfBook, 'bid' | 'ask'>,
): { limit: number; stop: number; base: number } | { error: string } {
  const base = action.kind === 'short_limit_ask_offset' ? book.ask : book.bid;
  if (base == null || !(base > 0)) return { error: NOVA_ACTION_DEPTH_DISABLED_REASON };
  const limit = cents(base + (action.params.offsetDollars ?? NOVA_ACTION_DEFAULT_SHORT_OFFSET_DOLLARS));
  if (!(limit > 0)) return { error: 'Computed limit price is invalid' };
  return { limit, stop: cents(limit + shortStopOffset(action)), base };
}

async function send(
  runtime: NovaActionRuntime,
  symbol: string,
  side: 'BUY' | 'SELL',
  qty: number,
  extra: { limit_price: number; short_entry?: boolean; stop_loss_price?: number },
  base: number,
  actionTiming: BrowserActionStamp,
  idempotencyKey: string,
): Promise<NovaActionResult> {
  const mode = accountModeLabel(runtime.accountMode);
  try {
    const res = await placeIbkrOrder(
      { symbol, side, qty, order_type: 'LMT', outside_rth: false, ...extra },
      idempotencyKey,
      { timing: beginBrowserExecutionTiming('nova_action_place', actionTiming), referencePrice: base },
    );
    return {
      ok: res.ok,
      text: res.ok ? `Order #${res.order_id} placed` : res.error ?? 'Order failed',
      ...(!res.ok ? { reasonCode: res.reason_code, order: { symbol, side, qty, mode } } : {}),
    };
  } catch {
    return { ok: false, text: 'Network error placing order' };
  }
}

export async function runShortHotkey(
  action: NovaActionRecord,
  runtime: NovaActionRuntime,
  symbol: string,
  actionTiming: BrowserActionStamp,
  maybeConfirm: Confirm,
  idempotencyKey: string,
): Promise<NovaActionResult> {
  // Every one of these reads the position: a short never opens on a long, a cover never on nothing.
  if (runtime.accountError) return { ok: false, text: NOVA_ACTION_ACCOUNT_ERROR_MESSAGE };
  const held = runtime.position?.qty ?? 0;
  const mode = accountModeLabel(runtime.accountMode);

  if (action.kind === 'cover_pos') {
    if (!(held < 0)) return { ok: false, text: SHORT_HOTKEY_NO_SHORT(symbol) };
    return placeMarketExit(
      runtime, symbol, 'BUY', Math.abs(held), 'cover all', actionTiming, maybeConfirm, idempotencyKey, 'flatten',
    );
  }

  const tobOrErr = requireDepth(runtime, symbol);
  if ('ok' in tobOrErr && tobOrErr.ok === false) return tobOrErr;
  const tob = tobOrErr as TopOfBook;

  if (action.kind === 'cover_limit_ask_offset') {
    if (!(held < 0)) return { ok: false, text: SHORT_HOTKEY_NO_SHORT(symbol) };
    if (tob.ask == null || !(tob.ask > 0)) return { ok: false, text: NOVA_ACTION_DEPTH_DISABLED_REASON };
    const limit = cents(tob.ask + (action.params.offsetDollars ?? NOVA_ACTION_DEFAULT_OFFSET_DOLLARS));
    const qty = Math.abs(held);
    if (!(await maybeConfirm(runtime, `COVER ${qty} ${symbol} (BUY LMT @ $${limit.toFixed(2)}) on ${mode} account.`))) {
      return { ok: false, text: 'Order cancelled' };
    }
    return send(runtime, symbol, 'BUY', qty, { limit_price: limit }, tob.ask, actionTiming, idempotencyKey);
  }

  if (held > 0) return { ok: false, text: SHORT_WHY_LONG(symbol) };
  const plan = planShortHotkey(action, tob);
  if ('error' in plan) return { ok: false, text: plan.error };
  const shares = action.params.shares ?? NOVA_ACTION_DEFAULT_SHARES;
  const summary =
    `SHORT ${shares} ${symbol} (LMT @ $${plan.limit.toFixed(2)}, buy stop $${plan.stop.toFixed(2)}) on ${mode} account.`;
  if (!(await maybeConfirm(runtime, summary))) return { ok: false, text: 'Order cancelled' };
  return send(
    runtime, symbol, 'SELL', shares,
    { limit_price: plan.limit, short_entry: true, stop_loss_price: plan.stop },
    plan.base, actionTiming, idempotencyKey,
  );
}
