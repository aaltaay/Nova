/**
 * The header padlock's tooltip: what the backend latch says and what a click
 * will do (lock, one-click unlock on Paper / Sim, the Live PIN, or set the PIN first).
 */
import {
  TICKER_TRADE_LOCK_ICON_ARMED_BLOCKED_TITLE,
  TICKER_TRADE_LOCK_ICON_LOCKED_NO_PIN_TITLE,
  TICKER_TRADE_LOCK_ICON_LOCKED_TITLE,
  TICKER_TRADE_LOCK_ICON_PIN_NOT_SET_TITLE,
  TICKER_TRADE_LOCK_ICON_UNLOCKED_BY_BOT_TITLE,
  TICKER_TRADE_LOCK_ICON_UNLOCKED_TITLE,
} from '../constants';
import type { TradingAllowed } from './tradingAllowed';
import type { IbkrStatus } from './types';

type ArmFacts = Pick<IbkrStatus, 'armed_by' | 'arm_requires_pin' | 'live_arm_pin_set'>;

export function padlockTitle(
  status: ArmFacts,
  gate: TradingAllowed & { sessionUnlocked: boolean },
): string {
  if (gate.sessionUnlocked) {
    if (gate.allowed) {
      return status.armed_by === 'bot'
        ? TICKER_TRADE_LOCK_ICON_UNLOCKED_BY_BOT_TITLE
        : TICKER_TRADE_LOCK_ICON_UNLOCKED_TITLE;
    }
    return gate.reason
      ? `${TICKER_TRADE_LOCK_ICON_ARMED_BLOCKED_TITLE} ${gate.reason}`
      : TICKER_TRADE_LOCK_ICON_ARMED_BLOCKED_TITLE;
  }
  const base = status.arm_requires_pin === false
    ? TICKER_TRADE_LOCK_ICON_LOCKED_NO_PIN_TITLE
    : status.live_arm_pin_set === false
      ? TICKER_TRADE_LOCK_ICON_PIN_NOT_SET_TITLE
      : TICKER_TRADE_LOCK_ICON_LOCKED_TITLE;
  // The PIN blocker's own reason repeats the title; any other blocker adds news.
  const extra = gate.blockers.some((b) => b !== 'pin') ? gate.reason : null;
  return extra ? `${base} ${extra}` : base;
}
