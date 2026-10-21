/** Why the heat map shows no lines, in the desk's words (no silent blank screen): null when it draws normally. */
import {
  HEAT_ALIVE_GRACE_SEC,
  HEAT_ET_ZONE,
  HEAT_L1_ONLY,
  heatLineDown,
  heatStale,
  heatWaiting,
} from './heatMapConstants';
import { heatPendingLine, type HeatSymbol } from './heatStore';

/** Seconds past the line's last sign of life before the view says it went quiet. */
const QUIET_SEC = 8;

export function heatStatus(s: HeatSymbol | null, symbol: string, wallMs: number): string | null {
  const line = s?.line ?? heatPendingLine(symbol);
  if (line) return heatLineDown(line.why);
  if (!s || s.snaps.length === 0) return heatWaiting(symbol);
  if (s.l1) return HEAT_L1_ONLY;
  // Quiet = the depth socket went silent (no book or beat) on the browser clock, on any venue: a paused replay keeps
  // beating and stays quiet here; a dropped socket says so.
  if (wallMs - s.depthWallMs > (HEAT_ALIVE_GRACE_SEC + QUIET_SEC) * 1000) {
    const clock = new Date(s.aliveT * 1000).toLocaleTimeString('en-US', { timeZone: HEAT_ET_ZONE, hour12: false });
    return heatStale(clock);
  }
  return null;
}
