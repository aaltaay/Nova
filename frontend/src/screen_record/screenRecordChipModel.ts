/**
 * What the header says about the trading screen recording (ADR 035, ADR 067).
 * Paused by default: a muted monitor with a slash and "Screen rec paused", how
 * to turn it on in the tip -- stated, never an alarm. Once on, quiet while
 * every monitor records -- an icon, the details on hover -- and loud the
 * moment one does not. Pure: the view in, the chip out.
 */
import type { ScreenRecordDisplay, ScreenRecordView } from './screenRecordView';

/** `off`: nothing is recorded, by the setting or because no desktop app records -- muted, no recording dot. */
export type ScreenChipTone = 'off' | 'quiet' | 'warn' | 'loud';

export interface ScreenChip {
  tone: ScreenChipTone;
  /** Words on the chip; null shows the icon alone (all is well). */
  label: string | null;
  title: string;
  tip: string;
}

export const SCREEN_CHIP_TITLE = 'Screen recording';
export const SCREEN_CHIP_PAUSED_LABEL = 'Screen rec paused';
/** How the operator turns it on (ADR 067): the desk setting, read when the desktop app starts. */
export const SCREEN_RECORD_ON_HOW = "To record every monitor, set NOVA_SCREEN_RECORD=1 in Nova's .env and restart Nova.";
export const SCREEN_RECORD_OFF_HOW = "On by NOVA_SCREEN_RECORD=1: remove it from Nova's .env and restart Nova to pause the recording.";
export const SCREEN_CHIP_BROWSER_LABEL = 'Screen not recorded';
export const SCREEN_CHIP_BROWSER_TIP =
  'This browser window cannot record your screen: only the desktop app can, and it is paused by default.\n'
  + "To record every monitor, set NOVA_SCREEN_RECORD=1 in Nova's .env and open Nova from the desktop app.";

const ET_TIME = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  hourCycle: 'h23',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

export function etTime(epochSec: number): string {
  return `${ET_TIME.format(new Date(epochSec * 1000))} ET`;
}

/** Sizes as Windows Explorer shows them (1024-based), like the diagnostics checklist. */
export function sizeLabel(bytes: number): string {
  const gb = bytes / 1024 ** 3;
  if (gb < 1) return `${Math.round(bytes / 1024 ** 2)} MB`;
  return gb < 10 ? `${gb.toFixed(1)} GB` : `${Math.round(gb)} GB`;
}

function codecLabel(mime: string | null): string {
  if (!mime) return 'video';
  if (/h264|avc1/i.test(mime)) return 'H.264';
  if (/vp9/i.test(mime)) return 'VP9';
  if (/vp8/i.test(mime)) return 'VP8';
  return mime;
}

const monitors = (n: number) => (n === 1 ? '1 monitor' : `${n} monitors`);

function displayLine(d: ScreenRecordDisplay): string {
  const name = `Monitor ${d.index}${d.primary ? ' (main)' : ''}`;
  if (d.recording) return `${name}: ${d.width}x${d.height} -> ${d.file ?? 'starting a file'}`;
  const retry = d.retryAt ? `, trying again at ${etTime(d.retryAt)}` : '';
  return `${name}: NOT RECORDING -- ${d.error ?? 'starting'}${retry}`;
}

function driveLine(view: ScreenRecordView): string | null {
  const free = view.disk.freeBytes;
  if (free === null) return 'Free space on the recording drive: unknown';
  const drive = /^[A-Za-z]:/.test(view.dir) ? view.dir.slice(0, 2) : 'The recording drive';
  return `${drive} has ${sizeLabel(free)} free`;
}

function problemLines(view: ScreenRecordView): string[] {
  return view.problems.slice(0, 3).map((p) => {
    const back = p.resumedAt ? `, back at ${etTime(p.resumedAt)}` : ', not back yet';
    return `${etTime(p.at)}: monitor ${p.displayIndex} stopped (${p.detail})${back}`;
  });
}

function pausedTip(view: ScreenRecordView): string {
  const lines = [
    'Screen recording is paused (off by default): no monitor is recorded.',
    SCREEN_RECORD_ON_HOW,
    `Once on: every monitor from launch to quit, ${view.fps} fps, a new file per monitor every ${view.segmentMin} minutes, in ${view.dir || 'the recording folder'}.`,
  ];
  if (view.dirNote) lines.push(view.dirNote);
  return lines.join('\n');
}

export function screenChip(view: ScreenRecordView | null, desktop: boolean): ScreenChip {
  if (!desktop) return { tone: 'off', label: SCREEN_CHIP_BROWSER_LABEL, title: SCREEN_CHIP_TITLE, tip: SCREEN_CHIP_BROWSER_TIP };
  // No answer yet: no recording dot until the desktop app says the screen records.
  if (!view) return { tone: 'off', label: null, title: SCREEN_CHIP_TITLE, tip: 'Asking the desktop app whether the screen is recorded.' };
  if (view.state === 'paused') return { tone: 'off', label: SCREEN_CHIP_PAUSED_LABEL, title: SCREEN_CHIP_TITLE, tip: pausedTip(view) };

  const n = view.displays.length;
  const on = view.displays.filter((d) => d.recording).length;
  const lines: string[] = [];
  switch (view.state) {
    case 'recording':
      lines.push(`Recording ${n === 1 ? 'the' : 'all'} ${monitors(n)}${view.since ? ` since ${etTime(view.since)}` : ''}.`);
      break;
    case 'starting':
      lines.push(`Starting to record ${n ? monitors(n) : 'every monitor'}.`);
      break;
    case 'partial':
      lines.push(`Only ${on} of ${n + view.unmatched} monitors are being recorded. Nova keeps trying.`);
      break;
    case 'suspended':
      lines.push('The PC went to sleep; recording starts again when it wakes.');
      break;
    default:
      lines.push(`YOUR SCREEN IS NOT BEING RECORDED${view.error ? `: ${view.error}` : '.'}`);
      lines.push('Nova keeps trying on its own (at least once a minute).');
  }
  lines.push(...view.displays.map(displayLine));
  if (view.unmatched) lines.push(`${monitors(view.unmatched)} Windows did not offer for capture.`);
  lines.push(`Folder: ${view.dir || 'unknown'}`);
  if (view.dirNote) lines.push(view.dirNote);
  lines.push(`${codecLabel(view.mime)}, ${view.fps} fps, a new file every ${view.segmentMin} minutes. Nova never deletes a recording.`);
  const drive = driveLine(view);
  if (drive) lines.push(drive);
  lines.push(SCREEN_RECORD_OFF_HOW);
  const problems = problemLines(view);
  if (problems.length) lines.push('', 'Recent stops:', ...problems);
  const tip = lines.join('\n');

  if (view.state === 'failed' || view.state === 'stopped') {
    return { tone: 'loud', label: 'Screen not recording', title: SCREEN_CHIP_TITLE, tip };
  }
  if (view.state === 'partial') {
    return { tone: 'loud', label: `Screen: ${on} of ${n + view.unmatched} recorded`, title: SCREEN_CHIP_TITLE, tip };
  }
  if (view.disk.state === 'fail' && view.disk.freeBytes !== null) {
    return { tone: 'loud', label: `Screen: ${sizeLabel(view.disk.freeBytes)} left`, title: SCREEN_CHIP_TITLE, tip };
  }
  if (view.dirSource === 'fallback') {
    return { tone: 'warn', label: 'Screen on system drive', title: SCREEN_CHIP_TITLE, tip };
  }
  if (view.disk.state === 'warn' && view.disk.freeBytes !== null) {
    return { tone: 'warn', label: `Screen: ${sizeLabel(view.disk.freeBytes)} free`, title: SCREEN_CHIP_TITLE, tip };
  }
  return { tone: 'quiet', label: view.state === 'suspended' ? 'Screen paused (sleep)' : null, title: SCREEN_CHIP_TITLE, tip };
}
