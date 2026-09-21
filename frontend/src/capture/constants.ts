/** Maximum age of server recording evidence before tabs release their close lock. */
export const CAPTURE_STATUS_FRESH_MS = 15_000;

/**
 * A running recording is quiet state; a stop the operator did not ask for is
 * the loud one (operator decision, 2026-09-21). These strings are the whole
 * vocabulary of both.
 */
export const RECORDING_CHIP_ROLE = 'REC';
export const RECORDING_SIGNAL_TICK_MS = 1000;
export const recordingChipValue = (symbol: string, elapsed: string): string => `${symbol} · ${elapsed}`;
export const recordingHairlineTitle = (symbol: string): string => `Recording ${symbol}`;
export const recordingChipTitle = (args: {
  symbol: string; elapsed: string; segment: number | null; prints: number; quotes: number; l2: number;
  lastWriteAgeSec: number | null; reacquired: number; dir: string | null;
}): string => {
  const lines = [
    `Recording ${args.symbol} for ${args.elapsed}${args.segment && args.segment > 1 ? ` (segment ${args.segment})` : ''}`,
    `${args.prints.toLocaleString()} prints · ${args.quotes.toLocaleString()} quotes · ${args.l2.toLocaleString()} L2 books`,
    args.lastWriteAgeSec == null ? 'Nothing written yet' : `Last write ${args.lastWriteAgeSec}s ago`,
  ];
  if (args.reacquired) lines.push(`IBKR lines re-acquired ${args.reacquired}x after a Gateway drop`);
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
};
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
export const RECORDING_DISMISS_LABEL = 'Dismiss';

/** Stop needs friction: a recording is locked, and a slip must not end it. */
export const CAPTURE_STOP_HOLD_MS = 1200;
export const CAPTURE_STOP_HOLD_STEP_MS = 50;
export const captureStopHoldLabel = (symbol: string): string => `Hold to stop recording ${symbol}`;
export const CAPTURE_STOP_HOLD_HINT = 'Press and hold. Letting go early keeps recording.';
