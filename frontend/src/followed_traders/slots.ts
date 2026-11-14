/**
 * What another feature may draw on the followed traders' page (ADR 005: the page imports no other feature): something
 * in the head, in the middle of a trader's card, and a chip on an open row. LiveTrader Bots filled them with the Live
 * Trader bot's key, card and BOT chip until ADR 072 retired that bot; the TraderTV page passes none. Each slot is a
 * component that reads its own data, so the page never re-renders for it.
 */
import { createContext, useContext, type ComponentType } from 'react';
import type { FollowedTrade } from './types';

export interface FollowedSlots {
  /** In the head, after the title. */
  Head?: ComponentType;
  /** In the middle of a trader's card, between their record and their P/L, on today only; `open` is what they hold. */
  Trader?: ComponentType<{ name: string; open: readonly FollowedTrade[] }>;
  /** Beside the ticker of an open position's row, on today only. */
  OpenBadge?: ComponentType<{ trade: FollowedTrade }>;
}

const NONE: FollowedSlots = {};

export const FollowedSlotsContext = createContext<FollowedSlots>(NONE);

export function useFollowedSlots(): FollowedSlots {
  return useContext(FollowedSlotsContext);
}
