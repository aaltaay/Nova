/**
 * Runtime shape for Nova Action execution (shared across executor modules).
 */

import { ownerBotsHoldSentence } from '../constantGroups/owners';
import type { IbkrPosition } from '../ibkr';
import type { TopOfBook } from './TopOfBookContext';

export interface NovaActionRuntime {
  symbol: string | null;
  connected: boolean;
  spendStatus?: string;
  /** paper | live | disconnected — shown in confirm dialogs. */
  accountMode?: string;
  /** Set when useIbkrAccount last poll failed — block exit/flatten actions. */
  accountError?: string | null;
  position: IbkrPosition | null;
  /** The bots' shares in the symbol, signed (ADR 069). For a refusal's words only: nothing sizes from it. */
  botsQty?: number;
  topOfBook: TopOfBook | null;
  /** Called when place-confirm is required; return true to proceed. */
  requestConfirm?: (summary: string) => Promise<boolean>;
}

/**
 * A refusal for shares you do not hold says where they are while the bots hold them (ADR 069 decision 9): `side`
 * narrows it to what the action wanted, a short to cover or a long to sell.
 */
export function refusalNamingBots(text: string, runtime: NovaActionRuntime, side?: 'long' | 'short'): string {
  const yours = runtime.position?.qty ?? 0;
  const bots = runtime.botsQty ?? 0;
  const theirs = side === 'short' ? yours >= 0 && bots < 0 : side === 'long' ? yours <= 0 && bots > 0 : yours === 0 && bots !== 0;
  return theirs ? text + ownerBotsHoldSentence(bots) : text;
}
