/**
 * Typed Nova Actions (Phase G3) — executable intents, never raw DAS scripts.
 */

import type { NovaActionKind } from '../constants';
import type { HotkeyKeyChord } from './types';

export interface NovaActionParams {
  shares?: number;
  /** Dollar offset from Ask/Bid (e.g. 0.05). */
  offsetDollars?: number;
  /** Exit percent of position (e.g. 50). */
  percent?: number;
  /** Force IB outsideRth (extended hours) on this place. */
  outsideRth?: boolean;
}

export interface NovaActionRecord {
  id: string;
  name: string;
  kind: NovaActionKind;
  key: HotkeyKeyChord;
  params: NovaActionParams;
  enabled: boolean;
  showButton: boolean;
}

export type NovaActionResult = {
  ok: boolean;
  text: string;
  reasonCode?: string | null;
  order?: {
    symbol: string;
    side: string;
    qty: number;
    mode?: string | null;
  };
};

/**
 * A result as the dispatcher publishes it (`lastResult`): `seq` changes on
 * every run, so a repeat of the same text is still a new outcome, and
 * `symbol` is the one the action ran on -- the ticket for that symbol shows
 * it on its Last line (QA R35).
 */
export type NovaActionOutcome = NovaActionResult & {
  seq: number;
  symbol: string | null;
};
