/**
 * The Followed traders page. Mirrors backend/followed_traders/constants_followed.py
 * (FOLLOWED_SCHEMA_VERSION, FOLLOWED_CAPTURE_STALE_SEC). Schema: architecture/schema/followed-traders.md.
 */

export const FOLLOWED_SCHEMA_VERSION = 1;
export const FOLLOWED_CONFIG_PATH = '/api/followed-traders/config';
export const FOLLOWED_DAY_PATH = '/api/followed-traders/day';
export const FOLLOWED_RECORD_PATH = '/api/followed-traders/record';
export const FOLLOWED_READS_PATH = '/api/followed-traders/reads';

/** The page asks this often while it shows. */
export const FOLLOWED_REFRESH_MS = 3_000;
/** A Week or All record is asked again this often while it shows (its exits fill in as IBKR is read). */
export const FOLLOWED_RECORD_REFRESH_MS = 15_000;
/** The desk's trade toasts ask the feed (without prices) this often. */
export const FOLLOWED_TOAST_POLL_MS = 5_000;
/** A toast leaves on its own after this long; hovering holds it. */
export const FOLLOWED_TOAST_TTL_MS = 20_000;
/** At most this many toasts show at once (the oldest leaves first). */
export const FOLLOWED_TOAST_MAX = 4;
/** The gate probe asks again this soon when the backend did not answer at all (still starting). */
export const FOLLOWED_PROBE_RETRY_MS = 10_000;
/** The feed's capture reads stale when its status is older than this. */
export const FOLLOWED_CAPTURE_STALE_SEC = 60;
/** Blob URLs of the feed's images kept for reuse before the oldest is released. */
export const FOLLOWED_IMAGE_CACHE = 80;
/** Local storage key of the Alerts switch (a per-window convenience; on by default). */
export const FOLLOWED_ALERTS_KEY = 'nova.followed.alerts';
/** Local storage key of the stream player's open / closed (a per-window convenience; open by default). */
export const FOLLOWED_STREAM_KEY = 'nova.followed.stream';
/** The stream plays from YouTube's privacy-enhanced host, muted to start; Open on YouTube opens its watch page. */
export const YOUTUBE_EMBED_BASE = 'https://www.youtube-nocookie.com/embed/';
export const YOUTUBE_WATCH_BASE = 'https://www.youtube.com/watch?v=';
/** The room kept under the newest Activity events for the "+N earlier" line, in px. */
export const FT_FOLD_LINE_PX = 34;

export const FT_TITLE = 'Following';
export const FT_LOADING = 'Asking the feed…';
export const FT_OFF = 'The followed traders feed is not configured on this desk (NOVA_FOLLOW_FEED_URL in the backend’s .env).';
export const FT_UNREACHABLE = 'The feed is not answering';
export const FT_BAD_ANSWER = 'The feed answered something Nova cannot read';
export const FT_READ_FAILED = 'Nova’s backend did not answer:';
export const FT_NO_TRADES = 'The feed recorded no trades on this day.';
export const FT_NO_STATUS = 'The feed has not reported its capture yet';

export const FT_PILL_WAITING = 'Waiting for the stream';
export const FT_PILL_HIDDEN = 'Positions off screen · showing the last read';
export const FT_PILL_STOPPED = 'Capture stopped';

export const FT_BAR_NO_IMAGE = 'The feed sends no picture of this slot';
export const FT_BAR_STAND_IN = 'Their slot at their last change';
export const FT_SLOT_NOW = 'Their slot now';
export const FT_SLOT_LAST_READ = 'Their slot as last read';

export const FT_HOLDING = 'Holding now';
export const FT_HOLDING_END = 'Open at the day’s end';
export const FT_OFF_AIR = 'Off air';
export const FT_NO_TRADES_TODAY = 'no trades today';
export const FT_NO_TRADES_THAT_DAY = 'no trades that day';
export const FT_EXIT_IS_IBKR = 'exit = IBKR’s last trade when it left their bar';
export const FT_NEWEST_FIRST_SHORT = 'newest first';
export const FT_ALL_CLOSED = 'All closed trades';
export const FT_CLOSE_LIST = 'Close';
export const FT_RESULT_WORDS = { win: 'WIN', loss: 'LOSS', scratch: 'SCRATCH', unscored: 'UNSCORED' } as const;
export const FT_OPEN_CHIP = 'OPEN';
export const FT_NOW = 'now';
export const FT_WATCH_LIVE = 'Watch live';
export const FT_NO_STREAM = 'The feed has not named a stream it reads yet';
export const FT_STREAM_SHOWING = 'The stream is showing beside the Activity';
export const FT_STREAM_LIVE = 'LIVE';
export const FT_STREAM_MUTE = 'Mute';
export const FT_STREAM_UNMUTE = 'Unmute';
export const FT_STREAM_MUTED = 'Muted';
export const FT_STREAM_SOUND_ON = 'Sound on';
export const FT_STREAM_POP_OUT = 'Pop out';
export const FT_STREAM_POP_OUT_TIP = 'Watch it in a small window of its own';
export const FT_STREAM_CLOSE = 'Close the stream';
export const FT_STREAM_YOUTUBE = 'Open on YouTube';
export const FT_STREAM_TITLE = 'The followed traders’ live stream';
export const FT_STREAM_SIGN_IN = 'Sign in to YouTube';
export const FT_STREAM_SIGN_IN_TIP = 'YouTube asks this network to sign in before it plays ("confirm you’re not a bot"). Sign in once in Google’s own page; Nova keeps it and never sees your password.';
export const FT_STREAM_RELOAD = 'Reload the player';
export const FT_STREAM_OFFLINE = 'Offline';
export const FT_STREAM_NOT_READING = 'the feed is not reading a live stream right now';
export const FT_STREAM_LIVE_ONLY = 'Only a live stream plays here, never a past broadcast. It comes back on its own when the feed reads the next one.';
export const FT_LAST_STREAM = 'Last stream:';
export const FT_RESETS = 'Resets';
export const FT_CLOSED_TODAY = 'Closed today';
export const FT_CLOSED = 'Closed';
export const FT_NO_OPEN = 'No open positions';
export const FT_NO_CLOSED_TODAY = 'No closed trades yet today';
export const FT_NO_CLOSED = 'No closed trades that day';
export const FT_ON_AIR = 'On air';
export const FT_PROOF = 'Proof';
export const FT_OPEN_IN_TRADER = 'Open in the Trader';
export const FT_EST = 'est.';
export const FT_EST_TIP = 'The exit happened while the feed could not see the bar, so this is the low–high of IBKR’s trades in that window, never one invented fill.';

export const FT_RECORDS = 'Records';
export const FT_RECORD_RANGES = { day: 'Day', week: 'Week', all: 'All' } as const;
export const FT_EVERYONE = 'Everyone';
export const FT_RECORD_PENDING = 'exits still being read from IBKR';

export const FT_ACTIVITY = 'Activity';
export const FT_ACTIVITY_HINT = 'Newest first · click an event for its Proof';
export const FT_ACTIVITY_HINT_TRADER = 'Newest first · click an event to open it in the Trader';
export const FT_ALL_ACTIVITY = 'The whole day’s Activity';
export const FT_NO_ACTIVITY = 'Nothing happened on the bar this day.';
export const FT_ALREADY_OPEN = 'Already open when capture started';

export const FT_ALERTS_ON = 'Alerts on';
export const FT_ALERTS_OFF = 'Alerts off';
export const FT_ALERTS_TIP = 'A toast on any Nova page when a followed trader opens, adds to or closes a position.';
export const FT_PREV_DAY = 'Previous day with trades';
export const FT_NEXT_DAY = 'Next day with trades';
export const FT_NO_PREV_DAY = 'The feed has no earlier day';
export const FT_NO_NEXT_DAY = 'This is the newest day the feed has';
export const FT_TODAY = 'Today';
export const FT_OPEN_THIS_DAY = 'Open this day';
export const FT_PICK_DAY = 'Pick a day to see what they traded';
export const FT_DAY_EMPTY_WEEKEND = 'Market closed: no stream that day.';
export const FT_DAY_EMPTY = 'Nothing was captured that day.';
export const FT_FUTURE_DAY = 'That day has not happened yet';
export const FT_PREV_MONTH = 'Previous month';
export const FT_NEXT_MONTH = 'Next month';

export const FT_BACK = 'Following';
export const FT_CHECK_A_READ = 'Check a read';
export const FT_ENTRY = 'Entry';
export const FT_EXIT = 'Exit';
export const FT_WHAT_WAS_READ = 'What the vision read';
export const FT_NO_EVIDENCE = 'The feed saved no screenshot for this moment.';
export const FT_STILL_OPEN = 'Still open';
export const FT_CLOSE_NOT_SEEN = 'The feed never saw it close';
export const FT_READS_TITLE = 'Every read of the slot during this trade';
export const FT_READS_NONE = 'No read during this trade differed from what was logged.';
export const FT_READS_LOADING = 'Reading the feed’s read log…';
export const FT_NOT_ON_BAR = 'name not read (bar off screen, or the tag read as another name)';
export const FT_NO_POSITIONS = 'no positions';
export const FT_IGNORED = 'ignored';
export const FT_NEVER_EDITS = 'Nova only reads the feed: a wrong trade is fixed in the feed, never here.';

export const FT_EXIT_PENDING = 'reading tape…';
/** Pending with a reason: IBKR not connected, its history budget, a retry. */
export const FT_EXIT_WAITING = 'waiting for IBKR';
export const FT_EXIT_UNAVAILABLE = 'no price';
export const FT_UNSCORED = 'unscored';
export const FT_UNSCORED_TIP = 'Not scored: the exit is not one known price (a window, not read yet, or a close the feed never saw).';
export const FT_TOAST_REGION = 'Followed traders';
export const FT_TOAST_DISMISS = 'Dismiss';
