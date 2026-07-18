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

export type NovaActionResult = { ok: boolean; text: string };
