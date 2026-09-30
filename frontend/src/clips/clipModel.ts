/**
 * Share clips (ADR 039), what the desk shows, pure: the clock labels, a CLIP
 * chip's look and its card, the Record menu's video part with its locks, and
 * a Records row's words. Every lock carries its reason (ux/whyTip.ts).
 */
import {
  CLIP_BUSY_WHY,
  CLIP_HQ_FULL_WHY,
  CLIP_HQ_HINT_OFF,
  CLIP_NEED_DESKTOP_WHY,
} from './clipsConstants';
import type { ClipRowView, ClipsView, OpenClip } from './clipsView';

/** `0:40`, `12:40`, `1:02:03`. */
export function clockLabel(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}

const etFmt = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23', hour: '2-digit', minute: '2-digit', second: '2-digit' });
const etDay = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' });
/** `08:06:16`, Eastern. */
export const etClock = (ts: number): string => etFmt.format(new Date(ts * 1000));
/** `2026-09-24`, Eastern. */
export const etDate = (ts: number): string => etDay.format(new Date(ts * 1000));

export function bytesLabel(n: number | null): string {
  if (n === null || !Number.isFinite(n)) return '—';
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`;
  if (n >= 1024 ** 2) return `${Math.round(n / 1024 ** 2)} MB`;
  return `${Math.max(1, Math.round(n / 1024))} KB`;
}

export const openClipFor = (view: ClipsView | null, symbol: string | null): OpenClip | null =>
  (symbol && view?.open.find((o) => o.symbol === symbol)) || null;

/** Why a clip's tab is not showing, in words. */
export function hiddenWords(reason: string | null, showing: string | null): string {
  switch (reason) {
    case 'symbol':
      return showing ? `the tab shows ${showing}` : 'the tab shows another symbol';
    case 'minimized':
      return 'Nova is minimized';
    case 'document':
      return 'the window is hidden';
    case 'closed':
      return 'its window was closed';
    case 'not_open':
      return 'there is no Trader tab for it';
    default:
      return 'the Trader view is not on screen';
  }
}

export type ChipTone = 'rec' | 'warn' | 'dim' | 'bad';
export interface ChipModel {
  tone: ChipTone;
  time: string;
  hq: boolean;
  extra: string | null;
  lines: string[];
}

/** One open clip's chip: its time, its tone, a short extra word, and the lines of its card. */
export function chipModel(open: OpenClip, nowSec: number, warnSec: number): ChipModel {
  const time = clockLabel(nowSec - open.startedTs);
  const lines = [`Video clip · ${open.symbol} · ${time}`, `Began ${etClock(open.startedTs)} ET`, `Picture: ${open.symbol}'s Trader tab, header left out`];
  let tone: ChipTone = 'rec';
  let extra: string | null = null;
  const hq = open.hq;
  if (hq) {
    const left = hq.endsAt !== null ? hq.endsAt - nowSec : null;
    if (hq.lost) {
      tone = 'warn';
      extra = 'lost';
      lines.push(`High quality lost${hq.error ? ` (${hq.error})` : ''}: the screen recording fills in while Nova starts it again`);
    } else {
      lines.push(`Frames: high quality, 30 fps${left !== null ? ` (${clockLabel(left)} left)` : ''}, with the screen recording under it`);
      if (left !== null && left <= warnSec) {
        tone = 'warn';
        extra = `HQ ${clockLabel(left)}`;
        lines.push('At the end the clip goes on as a cut: nothing stops.');
      }
    }
  } else {
    lines.push('Frames: cut from the screen recording');
  }
  if (open.state === 'hidden') {
    tone = 'dim';
    extra = '· hidden';
    lines.push(`Hidden: ${hiddenWords(open.reason, open.showing)}. The clip keeps going; the export offers to cut this stretch.`);
  } else if (open.state === 'no_picture') {
    tone = 'bad';
    extra = 'no picture';
    lines.push('No picture: the screen recording is not seeing this monitor and High quality is off.');
  }
  lines.push('Click to stop · the export opens from the Stop toast');
  return { tone, time, hq: Boolean(hq), extra, lines };
}

export interface VideoMenuState {
  open: OpenClip | null;
  canStart: boolean;
  startWhy: string | null;
  /** The screen recording is not seeing the tab's monitor: a cut would be blank. */
  noScreen: boolean;
  hqLocked: boolean;
  hqWhy: string | null;
  hqNote: string;
  hqFree: number;
}

/** The Record menu's video part for `symbol`: what can start, and why not. */
export function videoMenuState({ desktop, view, symbol, busy }: {
  desktop: boolean;
  view: ClipsView | null;
  symbol: string;
  busy: boolean;
}): VideoMenuState {
  const open = openClipFor(view, symbol);
  const hqFree = view ? Math.max(0, view.hqMax - view.hqInUse) : 0;
  const tab = view?.tabs.find((t) => t.symbol === symbol && t.visible) ?? null;
  const noScreen = tab?.screenRecording === false;
  let startWhy: string | null = null;
  if (!desktop) startWhy = CLIP_NEED_DESKTOP_WHY;
  else if (!view) startWhy = 'The desktop app has not answered yet';
  else if (busy) startWhy = CLIP_BUSY_WHY;
  else if (!open && noScreen && hqFree === 0) startWhy = 'The screen recording is not seeing that monitor, and both high-quality captures are in use: stop one first.';
  const hqLocked = !desktop || !view || busy || noScreen || (hqFree === 0 && !open?.hq);
  let hqWhy: string | null = null;
  if (!desktop) hqWhy = CLIP_NEED_DESKTOP_WHY;
  else if (!view) hqWhy = 'The desktop app has not answered yet';
  else if (busy) hqWhy = CLIP_BUSY_WHY;
  else if (noScreen) hqWhy = 'On: the screen recording is not seeing this monitor, so High quality is the only picture';
  else if (hqFree === 0 && !open?.hq) hqWhy = CLIP_HQ_FULL_WHY;
  const inUse = view ? `${view.hqInUse} of ${view.hqMax} in use` : '';
  let hqNote = `${CLIP_HQ_HINT_OFF} · ${inUse}`;
  if (open?.hq) hqNote = `${inUse} · stops itself at ${clockLabel(view?.hqMaxSec ?? 1800)}`;
  else if (noScreen) hqNote = 'on: the only picture right now';
  return { open, canStart: startWhy === null, startWhy, noScreen, hqLocked, hqWhy, hqNote, hqFree };
}

/** A Records row's status in words, with its tone. */
export function statusWords(row: ClipRowView): { text: string; tone: 'rec' | 'muted' | 'busy' | 'ok' | 'bad' } {
  switch (row.status) {
    case 'recording':
      return { text: 'Recording', tone: 'rec' };
    case 'queued':
      return { text: 'Waiting to export', tone: 'busy' };
    case 'exporting': {
      const p = row.export?.progress;
      return { text: p !== null && p !== undefined ? `Exporting ${Math.round(p * 100)}%` : 'Exporting', tone: 'busy' };
    }
    case 'ready':
      return { text: 'Ready', tone: 'ok' };
    case 'failed':
      return { text: `Export failed${row.export?.error ? `: ${row.export.error}` : ''}`, tone: 'bad' };
    case 'cancelled':
      return { text: 'Export cancelled', tone: 'muted' };
    default:
      return { text: 'Not exported', tone: 'muted' };
  }
}

/** Where a clip's frames come from, in words. */
export function sourcesWords(row: ClipRowView): string {
  if (row.origin === 'last_n') return 'Cut (the last 5 min)';
  const cut = Math.max(0, row.lengthSec - row.hqSec - row.gapSec);
  if (row.hqSec <= 0) return 'Cut · 15 fps';
  if (cut < 1) return 'High quality · 30 fps';
  return `Mixed: HQ ${clockLabel(row.hqSec)}, cut ${clockLabel(cut)}`;
}

/** A Records row's picture, and whether it shows the header. */
export function pictureWords(row: ClipRowView): { text: string; warn: string | null } {
  const picture = row.export?.picture ?? row.picture;
  const blurred = row.export?.blur?.length ? ' · blurred' : '';
  if (picture === 'window') return { text: `Whole Nova window${blurred}`, warn: 'header in' };
  if (picture === 'monitor') return { text: `Whole monitor${blurred}`, warn: 'everything on screen' };
  if (picture === 'panels') return { text: `Panels${blurred}`, warn: null };
  return { text: `Trader tab${blurred}`, warn: null };
}
