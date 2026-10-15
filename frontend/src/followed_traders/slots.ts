/**
 * What another feature draws on the followed traders' page (ADR 005: the page imports no other feature). Bots >
 * LiveTrader Bots gives the LiveTrader Bots key for the head, each host's bot for the middle of their card, and a chip
 * for an open row the bot copies (operator, 2026-10-15). Each slot is a component that reads its own data, so the page
 * never re-renders for it. Schema: architecture/schema/bot.md, "The Live Trader bot".
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
