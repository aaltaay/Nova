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
/** A Sim tab with nothing loaded, off the live edge, says what Sim is so an empty pane is not read as live data. */
export const SIM_TAB_WHAT_SIM_IS =
  'Off the live edge, Sim shows only the loaded replay. Follow wall clock during today\'s session for live '
  + 'Level 2 and Time & Sales with fake money, or use the Paper venue.';

/**
 * The live edge (ADR 020 live-edge amendment): the Sim clock follows the wall
 * clock on today's date, so the tab is live -- quote, Level 2, Time & Sales
 * and bars from the same feed a Paper tab reads, fills against it. Scrub back
 * and the tab shows the loaded replay; Follow wall clock returns here.
 */
export const SIM_LIVE_EDGE_LABEL = 'Live edge';
export const SIM_LIVE_EDGE_TITLE =
  'Following the wall clock on today\'s session: Sim tabs show the live feed and fill against it, fake money. '
  + 'Scrub back to replay -- today\'s Session Record loads by itself when one exists.';
/** Session-bar source label at the edge (replaces HISTORICAL / CAPTURE / NO REPLAY). */
export const SIM_LIVE_EDGE_SOURCE = 'LIVE EDGE';
/** Session-bar note with nothing loaded at the edge -- never "load a replay", the desk is live. */
export const SIM_LIVE_EDGE_EMPTY_NOTE = 'Live edge: practise on the live feed; scrub back to replay';
/** Following the wall clock but not at the edge: outside today\'s session, a closed exchange day, or a replayed day. */
export const SIM_WALL_CLOCK_LABEL = 'Wall clock';
export const SIM_WALL_CLOCK_TITLE =
  'Following the wall clock, but not the live edge: outside today\'s 04:00-20:00 session, on a closed '
  + 'exchange day, or on a replayed past day. Tabs show the loaded replay.';
/** The quiet per-tab line at the edge; dismissable, never an offer. */
export const SIM_TAB_LIVE_EDGE_TITLE = 'Live edge';
export const SIM_TAB_LIVE_EDGE_NOTE = 'Following the wall clock; scrub back to replay.';
/**
 * The own-recording line in a Sim tab. The Day / Ticker pickers live in the Sim
 * strip's ⋯ menu under Load recording (QA 2026-09-22, V20: the old copy pointed
 * "above", where nothing is); an uncounted recording never reads "-1 prints" (C22).
 */
export const simTabOwnRecording = (symbol: string, date: string, prints: number | null, recording: boolean): string => {
  const count = prints != null && Number.isFinite(prints) && prints >= 0 ? `${prints.toLocaleString()} prints` : 'prints recorded';
  return `Your Session Record of ${symbol} (${date}, ${count}${recording ? ', still recording' : ''}) `
    + 'can replay now — open ⋯ on the Sim strip and pick it under Load recording.';
};
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
/**
 * A download that failed because IBKR did not answer: said in the past tense
 * with when, because the failure is the last attempt's, not the Gateway's
 * state now -- the header may well say READY (QA 2026-09-22, V38).
 */
export const simTabOfferNotAnswering = (label: string, attempt: number, max: number, failedAt?: string | null): string =>
  `IBKR didn't answer IB Gateway ${failedAt ? `at ${failedAt}` : 'on the last try'} -- retrying ${label} every minute (${attempt} of ${max}).`;
export const simTabOfferNotAnsweringGaveUp = (label: string, failedAt?: string | null): string =>
  `IBKR didn't answer IB Gateway${failedAt ? ` (last try ${failedAt})` : ''}, so ${label} hasn't downloaded. `
  + 'Check the Gateway window for a login, 2FA prompt or maintenance notice, then Reconnect.';
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

/** The thin lane under the scrubber band: where Nova itself recorded the band's symbol. */
export const simRecordedLaneTitle = (symbol: string, ranges: string) => `Recorded by Nova: ${symbol} ${ranges} ET`;
export const simRecordedLaneNoneTitle = (symbol: string, date: string) =>
  `Not recorded by Nova: no Session Record for ${symbol}${date ? ` on ${date}` : ''}`;

/* ── QA batch fix/qa-sim-replay (2026-09-22): request failures, loading, records ── */

/** A request failure with no server message says who failed -- never "Historical replay" for a clock or a listing. */
export const SIM_REQUEST_FAILED_DEFAULT = 'Nova request failed';
export const SIM_HISTORY_REQUEST_FAILED = 'Historical replay request failed';
/** A plain-text error body (Starlette's "Internal Server Error") is quoted only when this short. */
export const SIM_REQUEST_PLAIN_ERROR_MAX_CHARS = 160;

/** Session Record rows (Records page, Day / Ticker pickers): words, never raw manifest codes or a -1. */
export const CAPTURE_SOURCE_IBKR = 'ibkr';
export const CAPTURE_NOT_IBKR_REASON = 'Not a Session Record: synthetic data from the removed SIM1 instrument';
export const CAPTURE_EMPTY_REASON = 'Empty recording';
export const CAPTURE_PRINTS_PRESENT = 'prints present';
export const CAPTURE_PRINTS_PRESENT_SHORT = 'data present';
export const CAPTURE_PRINTS_RECORDING = 'recording…';
export const CAPTURE_STATUS_WORDS: Record<string, string> = {
  recording: 'Recording',
  stopped_partial_ok: 'Stopped',
  interrupted: 'Cut by a Nova restart',
  failed: 'Failed',
  generated_full_day: 'Synthetic (not a recording)',
};
export const CAPTURE_REASON_WORDS: Record<string, string> = {
  operator: 'Stopped',
  rotation: 'Rolled to a new day',
  failure: 'Stopped on its own',
  restart: 'Cut by a Nova restart',
};
/** A download that holds no seconds of its window says so -- never "Downloaded through 09:15:00". */
export const SIM_HISTORY_NOTHING_DOWNLOADED = 'nothing downloaded';
export const SIM_HISTORY_NOTHING_DOWNLOADED_LINE = 'Nothing downloaded yet.';
export const SIM_HISTORY_NO_TRADES_YET = 'No trades downloaded yet for this window';
/** The Sim bar's download summary names a stopped / failed / finished job only this long after its last update. */
export const SIM_HISTORY_SUMMARY_RECENT_SEC = 15 * 60;
/** A capture replay's own panes (R16): REPLAY on the tape, the recording's L2 state, a gap stated as one. */
export const SIM_CAPTURE_TAPE_TITLE = 'Your Session Record, replayed at the playhead. Nothing here is live.';
export const SIM_CAPTURE_TAPE_NOT_RECORDED = 'Not recorded at this moment -- a gap in the recording';
export const SIM_CAPTURE_L2_TITLE =
  'Level 2 from your Session Record, replayed at the playhead. Live halt and borrow state are hidden because they describe today, not this session.';
export const SIM_CAPTURE_L2_NONE_TITLE =
  'This Session Record holds no Level 2 for this moment. Live halt and borrow state are hidden because they describe today, not this session.';
/** A Sim tab's price off the live edge is the replay's (R10): these say why there is none. */
export const SIM_REPLAY_PRICE_NONE = 'No replay price for this symbol at the playhead';
export const SIM_REPLAY_PRICE_NOT_RECORDED = 'Not recorded at this moment -- a gap in the recording';
/** A capture selection still being read from disk: neither loaded nor failed (`replay_loading`). */
export const SIM_REPLAY_LOADING = 'Loading recording…';
export const SIM_REPLAY_LOADING_TITLE = 'Nova is reading this Session Record from disk; the desk shows it once it has loaded.';
