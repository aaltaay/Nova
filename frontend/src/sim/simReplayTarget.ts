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
import {
  TRADER_VENUE_TAG_LIVE_EDGE,
  TRADER_VENUE_TAG_NO_REPLAY,
  TRADER_VENUE_TAG_REPLAY,
} from '../constantGroups/trader_chrome';
import {
  SIM_RAIL_FAILED_NOTE,
  SIM_RAIL_LOADING_NOTE,
  SIM_RAIL_NO_REPLAY_NOTE,
  simRailOtherSymbolNote,
} from './simConstants';
import type { SimClockState } from './simClockTypes';

export type SimReplayTarget =
  /** Nothing to say: not Sim, clock not read yet, or this tab IS the replay. */
  | { kind: 'ok' }
  /**
   * The Sim clock follows the wall clock on today's date: the tab is live
   * (ADR 020 live-edge amendment). Whatever is loaded serves the scrub back.
   */
  | { kind: 'live-edge' }
  /** Sim desk with no capture and no historical window selected. */
  | { kind: 'none' }
  /** A replay is loaded, but of a different symbol than this tab. */
  | { kind: 'other-symbol'; replaySymbol: string }
  /** A capture selection is still being read from disk: neither loaded nor failed (C59). */
  | { kind: 'loading' }
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
  // At the live edge the tab is live whatever is loaded; the backend's flag is
  // the single truth for that, never inferred here from scrubbed/paused.
  if (clock.live_edge) return { kind: 'live-edge' };
  if (clock.replay_ok === false) {
    return { kind: 'failed', error: clock.replay_error || 'Replay failed to load' };
  }
  if (clock.replay_loading) return { kind: 'loading' };
  if (!LOADED_SOURCES.has(clock.replay_source ?? '')) return { kind: 'none' };
  const replaySymbol = (clock.replay_symbol ?? '').trim().toUpperCase();
  const tab = symbol.trim().toUpperCase();
  // A historical selection always names its symbol; a capture may not publish
  // one mid-transition. Silence beats a notice we cannot substantiate.
  if (!replaySymbol || !tab || replaySymbol === tab) return { kind: 'ok' };
  return { kind: 'other-symbol', replaySymbol };
}

/**
 * The state word of the quote card's Sim venue tag: `live edge` at the edge,
 * `replay` only while a replay is loaded (or loading), `no replay` otherwise --
 * the tag read "SIM · replay" with nothing loaded (QA 2026-09-22, V38). Null
 * before the clock is read: say nothing rather than guess.
 */
export function simVenueTagState(clock: SimClockState | null | undefined): string | null {
  if (!clock) return null;
  if (clock.live_edge) return TRADER_VENUE_TAG_LIVE_EDGE;
  if (clock.replay_loading || LOADED_SOURCES.has(clock.replay_source ?? '')) return TRADER_VENUE_TAG_REPLAY;
  return TRADER_VENUE_TAG_NO_REPLAY;
}

/**
 * What the quote rail says instead of its live panes on a Sim desk, or null to
 * let the normal panes render.
 *
 * Null is right in exactly three cases: not Sim at all; the live edge, where
 * the backend serves the live feed through the ordinary endpoints exactly as
 * it does for Paper; and a CAPTURE replay of this very symbol -- the backend
 * serves a recording through the ordinary quote / book / tape endpoints, so
 * those panes ARE the replay. A historical replay has its own rail branch
 * (the snapshot), so reaching here with one selected for this symbol only
 * means its first snapshot has not arrived yet. Everything else is a practice
 * desk with nothing for this ticker, and the live panes would badge
 * themselves LIVE over a past session.
 */
export function simRailNote(
  symbol: string,
  clock: SimClockState | null | undefined,
  sim: boolean,
): string | null {
  if (!sim) return null;
  if (!clock) return SIM_RAIL_LOADING_NOTE;
  const target = simReplayTarget(symbol, clock, sim);
  if (target.kind === 'live-edge') return null;
  if (target.kind === 'loading') return SIM_RAIL_LOADING_NOTE;
  if (target.kind === 'none') return SIM_RAIL_NO_REPLAY_NOTE;
  if (target.kind === 'failed') return SIM_RAIL_FAILED_NOTE;
  if (target.kind === 'other-symbol') {
    return simRailOtherSymbolNote(symbol.trim().toUpperCase(), target.replaySymbol);
  }
  return clock.replay_source === 'historical' ? SIM_RAIL_LOADING_NOTE : null;
}
