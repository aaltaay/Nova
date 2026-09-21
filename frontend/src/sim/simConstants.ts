/** SIM session + historical replay tunables (mirror backend/constants_sim.py). */
export const SIM_SESSION_OPEN_LABEL = '04:00';
export const SIM_SESSION_CLOSE_LABEL = '20:00';
export const SIM_SESSION_MINUTES = 16 * 60;
/** Historical job list and quote/tape snapshot refresh. */
export const SIM_HISTORY_POLL_MS = 1000;
export const SIM_ET_TIME_ZONE = 'America/New_York';
/** Time & Sales badge while historical replay feeds the tape. */
export const SIM_REPLAY_TAPE_STATUS = 'REPLAY';
/** Tape tooltip: where colours come from. Never from price movement. */
export const SIM_REPLAY_TAPE_SIDES_RECORDED =
  "Colours come from your local L2 recording, only where its quote held across the print's second. Other rows are uncoloured.";
export const SIM_REPLAY_TAPE_SIDES_NONE =
  'Uncoloured: a historical download has no quotes, and no local L2 recording covers these prints.';
export const SIM_REPLAY_TAPE_EMPTY = 'No prints yet at this replay time';
export const SIM_REPLAY_TAPE_NO_TRADES = 'Completed candles only -- download trades for Time & Sales';
/** Tape past the download edge: say so rather than show the edge's prints as current. */
export const simReplayTapeNotDownloaded = (fetching: boolean): string => (fetching
  ? 'Not downloaded yet -- the download is fetching this moment now.'
  : 'Not downloaded yet -- download this window to see its prints.');
export const simScrubberCoverageTitle = (ranges: string): string =>
  `Trades downloaded: ${ranges} ET. Drag anywhere -- a running download fetches there next.`;
/** Capture band: where the recording ran, and the gaps a restart or failure left. */
export const simCaptureBandTitle = (label: string): string =>
  `${label} ET. Striped stretches were not recorded.`;
const SIM_CAPTURE_GAP_REASONS: Record<string, string> = {
  restart: 'was cut by a Nova restart',
  failure: 'stopped on its own',
  operator: 'was stopped',
  rotation: 'rolled to a new day',
};
export const simCaptureGapTitle = (reason: string | null): string =>
  `Not recorded${reason ? ` -- the recording before this ${SIM_CAPTURE_GAP_REASONS[reason] ?? 'ended'}` : ''}`;
export const simCaptureMissingLabel = (missing: string): string => `${missing} missing`;
/** Level 2 header chip in replay (replaces live halt / shortability chips). */
export const SIM_REPLAY_L2_CHIP_LABEL = 'Replay';
export const SIM_REPLAY_L2_CHIP_VALUE = 'No L2 recorded';
export const SIM_REPLAY_L2_CHIP_TITLE =
  'An IBKR historical download carries trades only, and no local depth recording covers this moment. Live halt and borrow state are hidden because they describe today, not this session.';
/** Same chip once a locally recorded book covers the playhead second (#309). */
export const SIM_REPLAY_L2_RECORDED_VALUE = 'Recorded L2';
export const SIM_REPLAY_L2_RECORDED_TITLE =
  'Level 2 recorded locally for this session, replayed at the playhead. Live halt and borrow state are hidden because they describe today, not this session.';
/** Said inside the ladder, because the rail hides .ibkr-depth-fallback-badge. */
export const SIM_REPLAY_L2_EMPTY_NOTE = 'Level 2 was not recorded for this moment';

/** Requests are bounded; slow polls never overlap. */
export const SIM_REQUEST_TIMEOUT_MS = 15_000;
export const SIM_HISTORY_IDLE_POLL_MS = 5_000;
export const SIM_CAPTURE_POLL_MS = 15_000;
export const SIM_SCRUB_KEYBOARD_MS = 120;
/** Mirrors backend historical acquisition pacing, not an ETA prediction. */
export const SIM_HISTORY_PAGE_INTERVAL_SEC = 11;
export const SIM_HISTORY_LARGE_WINDOW_MINUTES = 240;
export const SIM_HISTORY_SYMBOL_PATTERN = /^[A-Z0-9][A-Z0-9. -]{0,19}$/;
/** Mirrors backend SIM_HISTORY_RETRY_INTERVAL_SEC: a failed job is refused a retry sooner. */
export const SIM_HISTORY_RETRY_INTERVAL_SEC = 16;
/** Mirrors backend SIM_HISTORY_GATEWAY_UNREACHABLE: both Gateway ports refused (not running). */
export const SIM_HISTORY_GATEWAY_UNREACHABLE = 'IB Gateway unreachable';
/** Mirrors backend SIM_HISTORY_GATEWAY_NOT_ANSWERING: Gateway took the connection, IBKR never answered. */
export const SIM_HISTORY_GATEWAY_NOT_ANSWERING = 'IBKR did not answer';
/** A stuck IBKR session is not a blip: retry slowly, a few times, then hand back. */
export const SIM_TAB_NOT_ANSWERING_RETRY_SEC = 60;
export const SIM_TAB_NOT_ANSWERING_MAX_ATTEMPTS = 5;
/** Automatic Gateway-unreachable retries per tab visit before Retry is handed back. */
export const SIM_TAB_HEAL_MAX_ATTEMPTS = 3;
/** How often a replay loaded mid-download re-selects to fold new prints in. */
export const SIM_PROGRESSIVE_RELOAD_MS = 10_000;
/**
 * One-click window: the open and the first two hours, not the whole session.
 *
 * Download cost scales with PRINTS, not with hours. The panel's 04:00-20:00
 * default is 3.5 minutes for SPY premarket and 10+ hours for a low-float runner
 * through RTH, because a 1000-print page covers minutes of a quiet tape and
 * seconds of a busy one. A bounded window around the open is what practice
 * actually needs, and the prompt always states it. Any other window: use
 * Historical replay.
 */
export const SIM_TAB_WINDOW_START = '09:15';
export const SIM_TAB_WINDOW_END = '11:30';

/**
 * Sim tab prompt. A Sim tab without its replay says so in one line and offers
 * the one thing to do about it -- download and load -- instead of pointing the
 * operator at a panel. Window defaults match the Historical replay panel.
 */
export const SIM_TAB_NO_REPLAY_TITLE = 'No replay loaded';
export const SIM_TAB_OTHER_SYMBOL_TITLE = 'Not the replayed symbol';
export const SIM_TAB_REPLAY_FAILED_TITLE = 'Replay failed to load';
export const SIM_TAB_CHARTS_ARCHIVED = 'Charts show archived bars until a replay loads.';
export const SIM_TAB_NO_WINDOW = 'Pick a window with Historical replay in the Sim session bar above.';
export const simTabOtherSymbolLead = (tab: string, replaySymbol: string): string =>
  `${replaySymbol} is loaded, so ${tab} won't fill.`;
export const simTabOfferDownload = (label: string, instead: boolean): string =>
  `Download and load ${label}${instead ? ' instead' : ''}?`;
export const simTabOfferReady = (label: string, instead: boolean): string =>
  `${label} is downloaded${instead ? ' -- load it instead?' : '.'}`;
export const simTabOfferDownloading = (label: string, progress: string, hasCoverage: boolean): string =>
  hasCoverage
    ? `Downloading ${label}${progress}. Load now -- new prints fold in as they land.`
    : `Downloading ${label}${progress}. It loads as soon as the first prints land.`;
export const simTabOfferStopped = (label: string, progress: string): string =>
  `${label} download stopped${progress}.`;
export const simTabOfferFailed = (label: string, error: string): string =>
  `${label} download failed: ${error}`;
export const simTabOfferBusy = (runningLabel: string): string =>
  `${runningLabel} is downloading, and the desk runs one download at a time.`;
export const simTabOfferGatewayDown = (label: string): string =>
  `IB Gateway isn't running. Start it and ${label} downloads and loads by itself.`;
export const simTabOfferGatewayWaiting = (label: string): string =>
  `Waiting for IB Gateway -- ${label} downloads as soon as it's up. Finish the login in the Gateway window if it asks.`;
export const simTabOfferRetrying = (label: string): string =>
  `IB Gateway is back -- retrying ${label}.`;
export const simTabOfferNotAnswering = (label: string, attempt: number, max: number): string =>
  `IBKR isn't answering IB Gateway -- retrying ${label} every minute (${attempt} of ${max}).`;
export const simTabOfferNotAnsweringGaveUp = (label: string): string =>
  `IBKR isn't answering IB Gateway, so ${label} can't download. Check the Gateway window for a login, 2FA prompt or maintenance notice.`;
export const SIM_TAB_ACTION_DOWNLOAD = 'Download';
export const SIM_TAB_ACTION_LOAD = 'Load';
export const SIM_TAB_ACTION_RESUME = 'Resume';
export const SIM_TAB_ACTION_RETRY = 'Retry';
export const SIM_TAB_ACTION_START_GATEWAY = 'Start Gateway & download';
export const SIM_TAB_ACTION_RECONNECT = 'Reconnect Gateway & retry';
export const SIM_TAB_ACTION_STOP = 'Stop';
export const SIM_TAB_ACTION_STOP_OTHER = 'Stop it & start this';
export const SIM_TAB_ACTION_STARTING = 'Starting...';
export const SIM_TAB_ACTION_LOADING = 'Loading...';
export const SIM_TAB_DISMISS_LABEL = 'Dismiss';
export const simTabGoToReplayLabel = (replaySymbol: string): string => `Go to ${replaySymbol}`;

/**
 * Sim rail honesty. With no replay loaded (or another symbol loaded) the desk
 * has no tape, quote or book for this ticker -- so the rail says that instead
 * of falling through to the live IBKR panes, which would badge themselves LIVE
 * on a practice desk replaying a past session.
 */
export const SIM_RAIL_NO_REPLAY_NOTE = 'No replay loaded -- no quote, Level 2 or Time & Sales.';
export const simRailOtherSymbolNote = (tab: string, replaySymbol: string): string =>
  `${replaySymbol} is the loaded replay -- no ${tab} quote, Level 2 or Time & Sales.`;
export const SIM_RAIL_FAILED_NOTE = 'Replay failed to load -- nothing to show.';
export const SIM_RAIL_LOADING_NOTE = 'Loading replay...';
