/**
 * Chord conflict checks between Nova Actions.
 */

import { chordsConflict, chordToBinding } from '../hooks/hotkeyUtils';
import type { NovaActionRecord } from './novaActionTypes';

/** Returns a human conflict message, or null if the chord is free / empty. */
export function novaActionConflictMessage(
  draft: NovaActionRecord,
  actions: NovaActionRecord[],
): string | null {
  if (!chordToBinding(draft.key)) return null;
  for (const other of actions) {
    if (other.id === draft.id) continue;
    if (chordsConflict(draft.key, other.key)) {
      return `Conflicts with Nova Action "${other.name}"`;
    }
  }
  return null;
}
