/** Why the heat map shows no lines, in the desk's words (no silent blank screen): null when it draws normally. */
import {
  HEAT_ET_ZONE,
  HEAT_L1_ONLY,
  heatLineDown,
  heatStale,
  heatWaiting,
} from './heatMapConstants';
import { heatAliveUntil, heatPendingLine, onReplayClock, type HeatSymbol } from './heatStore';

/** Seconds past the line's last sign of life before the view says it went quiet. */
const QUIET_SEC = 8;

export function heatStatus(s: HeatSymbol | null, symbol: string, wallMs: number): string | null {
  const line = s?.line ?? heatPendingLine(symbol);
  if (line) return heatLineDown(line.why);
  if (!s || s.snaps.length === 0) return heatWaiting(symbol);
  if (s.l1) return HEAT_L1_ONLY;
  // A paused replay is not a quiet line: its clock stands still, so there is nothing to say.
  if (onReplayClock(s)) return null;
  const now = wallMs / 1000 + s.offset;
  if (now > heatAliveUntil(s) + QUIET_SEC) {
    const clock = new Date(s.aliveT * 1000).toLocaleTimeString('en-US', { timeZone: HEAT_ET_ZONE, hour12: false });
    return heatStale(clock);
  }
  return null;
}
