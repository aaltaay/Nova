/**
 * The desk says each fill out loud (fillVoice.ts), mounted once with the app bar, never on the sample desk.
 * Every window keeps its place in the order rows; only the window that polls the account speaks, so a fill is
 * said once however many windows are open. A position that moves (the 1 s account poll) reads the order rows
 * at once, so the voice follows a fill by about a second instead of the 5 s order poll. The header mute
 * silences it (sound/).
 */
import { useEffect } from 'react';
import { speakDesk } from '../sound';
import { newFillVoiceState, readFills } from './fillVoice';
import {
  getIbkrAccountSnapshot,
  isIbkrAccountPollLeader,
  refreshIbkrOrdersNow,
  subscribeIbkrAccount,
} from './ibkrAccountPoller';
import type { IbkrPosition } from './types';

function positionsKey(positions: readonly IbkrPosition[]): string {
  return positions.map(p => `${p.symbol}:${p.qty}`).sort().join('|');
}

export function FillVoiceHost(): null {
  useEffect(() => {
    const state = newFillVoiceState();
    let held: string | null = null;
    const onSnap = () => {
      const snap = getIbkrAccountSnapshot();
      const positions = positionsKey(snap.positions);
      if (held !== null && positions !== held && snap.venue === state.venue) refreshIbkrOrdersNow();
      held = positions;
      const lines = readFills(state, snap);
      if (lines.length && isIbkrAccountPollLeader()) lines.forEach(line => speakDesk(line));
    };
    const unsubscribe = subscribeIbkrAccount(onSnap);
    onSnap();
    return unsubscribe;
  }, []);
  return null;
}
