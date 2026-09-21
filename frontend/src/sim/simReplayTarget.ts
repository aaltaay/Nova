/**
 * What a Sim tab must say about itself before the operator reads its panes.
 *
 * A Sim pane is empty for a *reason*, and the reason is not visible from the
 * pane: with nothing loaded there is no tape, quote or book, and with another
 * symbol loaded this tab will never fill however long you wait. Worse, the
 * charts keep painting archived bars either way (`chart_bars.py` routes Sim
 * reads through the bar archive), so the desk looks half alive and the operator
 * is left inferring the truth from which panels happen to be blank.
 *
 * These notices name the state and, where there is one, carry the way out.
 * Pure on purpose -- the rendering component stays trivial and this stays
 * testable without a DOM.
 */
import type { SimClockState } from './simClockTypes';

export type SimReplayTarget =
  /** Nothing to say: not Sim, clock not read yet, or this tab IS the replay. */
  | { kind: 'ok' }
  /** Sim desk with no capture and no historical window selected. */
  | { kind: 'none' }
  /** A replay is loaded, but of a different symbol than this tab. */
  | { kind: 'other-symbol'; replaySymbol: string }
  /** The selection was attempted and failed; the desk is empty, not loading. */
  | { kind: 'failed'; error: string };

const LOADED_SOURCES = new Set(['historical', 'capture']);

export function simReplayTarget(
  symbol: string,
  clock: SimClockState | null | undefined,
  sim: boolean,
): SimReplayTarget {
  // Only Sim can be "pointed at" a symbol. Paper/Live panes follow the tab.
  if (!sim) return { kind: 'ok' };
  // No clock yet is not the same as no replay -- never flash a notice on load.
  if (!clock) return { kind: 'ok' };
  if (clock.replay_ok === false) {
    return { kind: 'failed', error: clock.replay_error || 'Replay failed to load' };
  }
  if (!LOADED_SOURCES.has(clock.replay_source ?? '')) return { kind: 'none' };
  const replaySymbol = (clock.replay_symbol ?? '').trim().toUpperCase();
  const tab = symbol.trim().toUpperCase();
  // A historical selection always names its symbol; a capture may not publish
  // one mid-transition. Silence beats a notice we cannot substantiate.
  if (!replaySymbol || !tab || replaySymbol === tab) return { kind: 'ok' };
  return { kind: 'other-symbol', replaySymbol };
}
