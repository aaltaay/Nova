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
  /** Recorded because a lane watches it (ADR 071), not by hand. */
  auto?: boolean;
  /** Whose lane, and the bots' setup and why, in words ("the bots' lane · 5-minute flat top · near its trigger"). */
  autoWhy?: string | null;
}): string => {
  const resumed = Boolean(args.segment && args.segment > 1);
  const lines = [
    resumed
      ? `Recording ${args.symbol} for ${args.elapsed} -- segment ${args.segment} of a session that began ${args.sessionElapsed} ago`
      : `Recording ${args.symbol} for ${args.elapsed}`,
    `${args.prints.toLocaleString()} prints · ${args.quotes.toLocaleString()} quotes · ${args.l2.toLocaleString()} L2 books`,
    args.lastWriteAgeSec == null ? 'Nothing written yet' : `Last write ${args.lastWriteAgeSec}s ago`,
  ];
  if (args.auto) lines.push(LANE_RECORD_CHIP_LINE);
  if (args.auto && args.autoWhy) lines.push(args.autoWhy);
  if (args.reacquired) lines.push(`IBKR lines asked for again ${args.reacquired}x (a Gateway drop or a lost tape)`);
  if (args.dir) lines.push(args.dir);
  lines.push('Click to open the tab.');
  return lines.join('\n');
};

/** REC chip card: a recording a lane keeps (ADR 071). */
export const LANE_RECORD_CHIP_LINE = 'lane -- recorded while a lane watches it; it ends when the lane leaves, and Records turns it off';
/** Whose lane records the stock (ADR 071): Records and the REC chip's card. */
export const LANE_OWNER_WORDS: Record<'you' | 'claude' | 'bots', string> = {
  you: 'your lane', claude: "Claude's lane", bots: "the bots' lane",
};
/** Why the bots' lane is on a setup, after its name (Records and the REC chip's card, operator ask 2026-10-14). */
export const AUTO_RECORD_WHY_WORDS: Record<string, string> = {
  trade: 'in a trade being scored',
  near: 'near its trigger',
  armed: 'armed, waiting on its trigger',
};
/** The REC chip's card stops its recording with the Record menu's hold, from any page. */
export const RECORDING_CHIP_STOP = 'Hold to stop';
export const recordingChipHolding = (symbol: string): string => `Keep holding… stops ${symbol}`;
export const RECORDING_CHIP_RECORDS = 'Records';
export const RECORDING_CHIP_STOP_FAILED = 'Stop did not go through:';

/** Why a recording stopped, in the operator's words. */
export const RECORDING_STOP_REASONS: Record<string, string> = {
  failure: 'stopped on its own',
  restart: 'was cut by a Nova restart',
  operator: 'was stopped',
  rotation: 'rolled to a new day',
  auto: 'was stopped by auto-record (window ended or line yielded)',
  lane: 'ended with its lane',
  // #525: prints stopped while the recording ran; never a segment reason.
  tape: 'lost its IBKR tape -- no prints are being recorded',
};
/**
 * Stops somebody planned -- the operator's Stop, a lane's end (ADR 071), and auto-record's stops in recordings
 * made before it -- are quiet: never a toast, and the gap after them is not "missing".
 */
export const RECORDING_PLANNED_STOP_REASONS: ReadonlySet<string> = new Set(['operator', 'auto', 'lane']);
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
