/**
 * The pullback dip on the 1-minute pane (#847, operator ask 2026-10-12): the first pullback's run, bought at the
 * candle that bottoms its pullback -- a bottoming wick or the first green close. WATCH ONLY: drawn and scored, never
 * traded. Pink, a colour no trade, level or other setup uses:
 *
 *   - the leg, boxed and labelled, only while the dip is the plan's (otherwise the first pullback's lane draws the
 *     same leg, and one leg drawn twice is clutter);
 *   - the pullback, from the candle after the leg high to the candle that bottomed it (the newest while it waits),
 *     between its low and the leg high: dashed while it waits ("DIP 2 · wants a wick"), solid once it bought
 *     ("DIP · WICK", "DIP · 1ST GREEN");
 *   - the entry candle boxed from the pullback's low to its close, and on a bottoming wick a ring on that low.
 *
 * Not the plan's: the same in a dimmed pink, unlabelled. A dip that failed has no levels to draw: the legend's chip
 * and the story say why. The story under the pointer is `dipStory`. Pure: the lane in, the shapes out.
 */
import { DIP_COLORS, DIP_DIM } from './constants';
import { emptyDraw, type LaneDraw } from './flatTopShapes';
import type { LaneDrawOptions } from './laneShapes';
import { fmtPx } from './planMath';
import { hhmmEt } from './timeWords';
import type { SetupLane } from './types';

export const PULLBACK_DIP = 'pullback_dip';
/** The entry candle's tag on the chart, by the template's entry. */
export const DIP_TAGS: Record<string, string> = { wick: 'WICK', green: '1ST GREEN' };
/** What a waiting dip wants, in the box's few words (the backend's `forming.waiting`). */
const WANTS: Record<string, string> = { 'a bottoming wick': 'wants a wick', 'the first green close': 'wants a green close' };
const WATCH_ONLY = 'Watch only: Nova draws and scores it, and never trades it.';

export function isDipLane(setupType: string | null | undefined): boolean {
  return setupType === PULLBACK_DIP;
}

function num(x: unknown): number | null {
  return typeof x === 'number' && Number.isFinite(x) ? x : null;
}

function pct(x: number): string {
  return `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)}%`;
}

export function dipShapes(lane: SetupLane, lead: boolean, o: LaneDrawOptions, bar: number, hoverId: string): LaneDraw {
  const out = emptyDraw();
  const leg = lane.leg;
  if (!leg || lane.state === 'failed') return out;
  const setup = lane.setup && lane.state !== 'watching' ? lane.setup : null;
  const forming = setup ? null : lane.forming;
  const c = lead ? DIP_COLORS : DIP_DIM;
  const box = (t1s: number, t2s: number, p1: number, p2: number, fill: string, label: string | null, dashed: boolean,
    labelBelow = false) => {
    const t1 = o.toTime(t1s);
    const t2 = o.toTime(Math.max(t1s, t2s));
    if (t1 === null || t2 === null) return;
    out.boxes.push({ t1, t2, p1, p2, fill, stroke: c.line, dashed, label, labelColor: c.text, labelBelow, hoverId });
  };
  if (lead) box(o.legStart?.(leg) ?? leg.t - 5 * bar, leg.t, leg.low, leg.high, c.fill, `LEG ${pct(leg.pct)}`, false);
  const d = setup?.detail ?? {};
  const entryT = num(d.entry_bar_t);
  const lastT = lane.series?.bars_as_of ?? null;
  const endT = setup ? entryT ?? setup.armed_bar_t ?? lastT : lastT;
  // The pullback's low: the bought dip says it; a waiting one's stop sits its offset under it.
  const low = num(d.pullback_low) ?? (setup ? setup.stop : forming ? forming.stop : null);
  if (endT === null || low === null || endT <= leg.t) return out;
  const mode = String(d.entry_mode ?? '');
  const label = !lead ? null : setup ? `DIP · ${DIP_TAGS[mode] ?? 'BOUGHT'}`
    : `DIP ${forming?.bars ?? ''} · ${forming?.blocked ? 'held back' : WANTS[forming?.waiting ?? ''] ?? 'waiting'}`;
  box(leg.t + bar, endT, low, leg.high, c.fill, label, !setup, true);
  if (setup && entryT !== null) {
    const t = o.toTime(entryT);
    if (t !== null) {
      out.boxes.push({ t1: t, t2: t, p1: low, p2: setup.trigger, fill: c.candle, stroke: c.line, dashed: false,
        label: null, labelColor: c.text, hoverId });
      if (mode === 'wick') {
        out.dots.push({ t, price: low, color: c.line, fill: c.ring, label: lead ? 'bottom' : null, labelColor: c.text,
          hoverId });
      }
    }
  }
  return out;
}

/** The dip's story under the pointer: where it stands, the run, the candle it bought (or waits for), its levels. */
export function dipStory(lane: SetupLane): { title: string; lines: string[] } {
  const lines = [lane.reason || lane.state];
  const leg = lane.leg;
  if (leg) lines.push(`Run ${pct(leg.pct)} to ${fmtPx(leg.high)} (from ${fmtPx(leg.low)}): the high the pullback came off`);
  const s = lane.setup;
  if (s && lane.state !== 'watching') {
    const d = s.detail ?? {};
    const at = num(d.entry_bar_t);
    const how = d.entry_mode === 'green' ? `the first green close after ${num(d.red_bars) ?? '?'} red`
      : `a bottoming wick (${Math.round((num(d.wick_pct) ?? 0) * 100)}% of the candle, closing `
        + `${Math.round((num(d.close_pct) ?? 0) * 100)}% up it)`;
    lines.push(`Bought the dip${at !== null ? ` at the ${hhmmEt(at)} candle's` : ' at the'} close ${fmtPx(s.trigger)}: ${how}`);
    lines.push(`Entry ${fmtPx(s.entry)} · stop ${fmtPx(s.stop)} (under the pullback's low) · target 1 ${fmtPx(s.target1)}`);
  } else if (lane.forming) {
    const f = lane.forming;
    lines.push(f.blocked ? `Held back: ${f.blocked}`
      : `Waits for ${f.waiting ?? 'the candle that bottoms it'}: a close near ${fmtPx(f.trigger)} would buy ${fmtPx(f.entry)}, `
        + `stop ${fmtPx(f.stop)}, target 1 ${fmtPx(f.target1)}`);
  }
  lines.push(WATCH_ONLY);
  return { title: `Pullback dip · ${lane.state} · watch only`, lines };
}
