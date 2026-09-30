/**
 * The export dialog's model (ADR 039, mockup v1 board 4), pure: the settings
 * it starts from (the Trader tab, header out, the panels that carry the
 * operator's size and P&L blurred, hidden stretches cut), the wire shape, the
 * output line, the X length hint, and the timeline's scale and ticks.
 */
import { clockLabel, etClock } from './clipModel';
import { CLIP_PRIVATE_PANELS, CLIP_X_FREE_LIMIT_SEC, type ClipPanelId, type ClipPicture } from './clipsConstants';
import type { ClipRowView } from './clipsView';

export interface ExportSettings {
  startTs: number;
  endTs: number;
  picture: ClipPicture;
  panels: ClipPanelId[];
  blur: ClipPanelId[];
  cutHidden: boolean;
}

export interface ExportPlanView {
  out: { width: number; height: number; fps: number; bitrate: number };
  duration: number;
  counts: { hq_sec: number; screen_sec: number; hidden_sec: number; gap_sec: number; unknown_sec?: number; no_picture_sec: number };
}

export function defaultSettings(row: ClipRowView): ExportSettings {
  return {
    startTs: row.startedTs,
    endTs: row.endedTs ?? row.startedTs + row.lengthSec,
    picture: 'trader_tab',
    panels: ['charts', 'level2', 'tape'],
    blur: [...CLIP_PRIVATE_PANELS],
    cutHidden: true,
  };
}

export const settingsWire = (s: ExportSettings) => ({
  start_ts: s.startTs,
  end_ts: s.endTs,
  picture: s.picture,
  panels: s.panels,
  blur: s.blur,
  cut_hidden: s.cutHidden,
});

/** `MP4 (H.264) · 1200 × 700 · 30 fps · 3:03 after the cuts · up to 38 MB`, as parts. */
export function outputParts(plan: ExportPlanView): string[] {
  const mb = Math.max(1, Math.round((plan.out.bitrate * plan.duration) / 8 / 1024 ** 2));
  const cut = plan.counts.hidden_sec + plan.counts.gap_sec + (plan.counts.unknown_sec ?? 0) + plan.counts.no_picture_sec;
  const parts = ['MP4 (H.264)', `${plan.out.width} × ${plan.out.height}`, `${plan.out.fps} fps`];
  parts.push(cut >= 1 ? `${clockLabel(plan.duration)} after the cuts` : clockLabel(plan.duration));
  parts.push(`up to ${mb} MB`);
  return parts;
}

/**
 * Where the frames come from, in words: high quality where it ran, the screen
 * recording around it, and what is left out -- when Nova was down, when it was
 * not following the tab (before the clip, after its stop), with no picture.
 */
export function sourceLine(plan: ExportPlanView): string {
  const { hq_sec: hq, screen_sec: screen, gap_sec: gap, unknown_sec: unknown = 0, no_picture_sec: none } = plan.counts;
  const parts: string[] = [];
  if (hq >= 1) parts.push(`high quality for ${clockLabel(hq)}`);
  if (screen >= 1) parts.push(`the screen recording for ${clockLabel(screen)}`);
  let line = parts.length ? `From ${parts.join(', ')}.` : '';
  if (gap >= 1) line += ` ${clockLabel(gap)} when Nova was down is left out.`;
  if (unknown >= 1) line += ` ${clockLabel(unknown)} when Nova was not following the tab is left out.`;
  if (none >= 1) line += ` ${clockLabel(none)} with no picture is left out.`;
  return line.trim();
}

/** A cut is the monitor's picture: say so while the export takes any of it from there. */
export function coverLine(plan: ExportPlanView, picture: string): string | null {
  if (picture === 'monitor' || plan.counts.screen_sec < 1) return null;
  return 'The screen recording shows what the monitor showed: a window over the tab is in the cut too. High quality records the tab itself.';
}

/** A clip longer than X takes from a free account, and what to do. */
export function xWarning(duration: number): string | null {
  if (duration <= CLIP_X_FREE_LIMIT_SEC) return null;
  return `${clockLabel(duration)} is longer than X takes from a free account (${clockLabel(CLIP_X_FREE_LIMIT_SEC)}). Trim ${clockLabel(duration - CLIP_X_FREE_LIMIT_SEC)}, or keep it for YouTube or Discord.`;
}

/** Epoch seconds to a share of the timeline's width, and back. */
export function timelineScale(from: number, to: number) {
  const span = Math.max(1, to - from);
  return {
    pct: (ts: number) => Math.min(100, Math.max(0, ((ts - from) / span) * 100)),
    ts: (pct: number) => from + (Math.min(100, Math.max(0, pct)) / 100) * span,
  };
}

/** Minute ticks (every 1, 2, 5, 10 or 15 min, whatever fits ten), `{ts, label}`. */
export function timelineTicks(from: number, to: number): { ts: number; label: string }[] {
  const span = Math.max(60, to - from);
  const step = [60, 120, 300, 600, 900, 1800, 3600].find((s) => span / s <= 10) ?? 3600;
  const out: { ts: number; label: string }[] = [];
  for (let t = Math.ceil(from / step) * step; t <= to; t += step) out.push({ ts: t, label: etClock(t).slice(0, 5) });
  return out;
}

/** A selection kept inside `[from, to]`, at least `minLen` long, start before end. */
export function clampSelection(start: number, end: number, from: number, to: number, minLen = 1): { start: number; end: number } {
  let s = Math.max(from, Math.min(start, to - minLen));
  const e = Math.min(to, Math.max(end, s + minLen));
  if (e - s < minLen) s = Math.max(from, e - minLen);
  return { start: s, end: e };
}
