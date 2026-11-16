/**
 * Runtime shape for Nova Action execution (shared across executor modules).
 */

import type { DeskVenue } from '../constantGroups/desk_venue';
import { ownerHoldSentence } from '../constantGroups/owners';
import type { IbkrPosition, OwnerHold } from '../ibkr';
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
  /** Another trader's shares in the symbol, signed (ADR 072). For a refusal's words only: nothing sizes from it. */
  othersHold?: OwnerHold | null;
  topOfBook: TopOfBook | null;
  /** Called when place-confirm is required; return true to proceed. */
  requestConfirm?: (summary: string) => Promise<boolean>;
  /** The venue this keypress landed on, read once by `runNovaAction`: every send names it (#1283). */
  venue?: DeskVenue | null;
}

/**
 * A refusal for shares you do not hold names the trader whose they are while another trader holds them (ADR 072):
 * `side` narrows it to what the action wanted, a short to cover or a long to sell.
 */
export function refusalNamingTrader(text: string, runtime: NovaActionRuntime, side?: 'long' | 'short'): string {
  const yours = runtime.position?.qty ?? 0;
  const other = runtime.othersHold;
  if (!other) return text;
  const theirs = side === 'short' ? yours >= 0 && other.qty < 0
    : side === 'long' ? yours <= 0 && other.qty > 0
      : yours === 0 && other.qty !== 0;
  return theirs ? text + ownerHoldSentence(other.owner, other.qty) : text;
}
