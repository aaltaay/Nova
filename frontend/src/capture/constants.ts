import { AUTO_RECORD_CHIP_LINE } from '../leaderboard/leaderboardConstants';

/** Maximum age of server recording evidence before tabs release their close lock. */
export const CAPTURE_STATUS_FRESH_MS = 15_000;

/**
 * A running recording is quiet state; a stop the operator did not ask for is
 * the loud one (operator decision, 2026-09-21). These strings are the whole
 * vocabulary of both.
 */
export const RECORDING_CHIP_ROLE = 'REC';
export const RECORDING_SIGNAL_TICK_MS = 1000;
/** Hover delay for the REC chip's card. The card is live (it counts up every tick),
 * so it is a rendered tooltip: a native `title` that changes each second flickers. */
export const RECORDING_CHIP_TOOLTIP_DELAY_MS = 200;
export const recordingChipValue = (symbol: string, elapsed: string): string => `${symbol} · ${elapsed}`;
export const recordingHairlineTitle = (symbol: string): string => `Recording ${symbol}`;
export const recordingChipTitle = (args: {
  symbol: string; elapsed: string; sessionElapsed: string; segment: number | null; prints: number; quotes: number;
  l2: number; lastWriteAgeSec: number | null; reacquired: number; dir: string | null;
  /** Started by auto-record (ADR 023), not by hand. */
  auto?: boolean;
}): string => {
  const resumed = Boolean(args.segment && args.segment > 1);
  const lines = [
    resumed
      ? `Recording ${args.symbol} for ${args.elapsed} -- segment ${args.segment} of a session that began ${args.sessionElapsed} ago`
      : `Recording ${args.symbol} for ${args.elapsed}`,
    `${args.prints.toLocaleString()} prints · ${args.quotes.toLocaleString()} quotes · ${args.l2.toLocaleString()} L2 books`,
    args.lastWriteAgeSec == null ? 'Nothing written yet' : `Last write ${args.lastWriteAgeSec}s ago`,
  ];
  if (args.auto) lines.push(AUTO_RECORD_CHIP_LINE);
  if (args.reacquired) lines.push(`IBKR lines asked for again ${args.reacquired}x (a Gateway drop or a lost tape)`);
  if (args.dir) lines.push(args.dir);
  lines.push('Click to open the tab. Stop from the tab menu (hold).');
  return lines.join('\n');
};

/** Why a recording stopped, in the operator's words. */
export const RECORDING_STOP_REASONS: Record<string, string> = {
  failure: 'stopped on its own',
  restart: 'was cut by a Nova restart',
  operator: 'was stopped',
  rotation: 'rolled to a new day',
  auto: 'was stopped by auto-record (window ended or line yielded)',
  // #525: prints stopped while the recording ran; never a segment reason.
  tape: 'lost its IBKR tape -- no prints are being recorded',
};
/**
 * Stops somebody planned -- the operator's Stop, auto-record's own stop
 * (ADR 023) -- are quiet: never a toast, and the gap after them is not "missing".
 */
export const RECORDING_PLANNED_STOP_REASONS: ReadonlySet<string> = new Set(['operator', 'auto']);
export const recordingStoppedTitle = (symbol: string, reason: string): string =>
  `${symbol} recording ${RECORDING_STOP_REASONS[reason] ?? 'stopped'}`;
export const recordingStoppedBody = (error: string | null, prints: number): string =>
  `${prints.toLocaleString()} prints are on disk.${error ? ` ${error}` : ''}`;
export const recordingResumeCountdown = (inSec: number, attempt: number, max: number): string =>
  `Resuming on its own in ${inSec}s (attempt ${attempt} of ${max}).`;
export const recordingResumeWaiting = (attempt: number, max: number): string =>
  `Resuming on its own once IBKR answers (attempt ${attempt} of ${max}).`;
export const recordingResumeGaveUp = (reason: string | null): string =>
  `Gave up resuming: ${reason ?? 'no reason given'}. Resume it yourself when the desk is back.`;
export const RECORDING_RESUME_ACTION = 'Resume now';
export const RECORDING_RESUMING_ACTION = 'Resuming...';
/** Why Resume now is locked while its own start is in flight (ux/whyTip.ts). */
export const RECORDING_RESUMING_WHY = 'Resuming the recording -- this unlocks when Nova answers.';
export const RECORDING_DISMISS_LABEL = 'Dismiss';

/** Stop needs friction: a recording is locked, and a slip must not end it. */
export const CAPTURE_STOP_HOLD_MS = 1200;
export const CAPTURE_STOP_HOLD_STEP_MS = 50;
export const captureStopHoldLabel = (symbol: string): string => `Hold to stop recording ${symbol}`;
export const CAPTURE_STOP_HOLD_HINT = 'Press and hold. Letting go early keeps recording.';

/* ── QA batch fix/qa-sim-replay (2026-09-22) ── */
/** A plain-text Record error body is quoted only when this short ("Internal Server Error"); HTML never. */
export const CAPTURE_COMMAND_PLAIN_ERROR_MAX_CHARS = 160;
