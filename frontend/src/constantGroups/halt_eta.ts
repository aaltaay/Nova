/** LULD / halt ETA chip copy and clock windows (mirrors backend halt_eta). */

export const LULD_PAUSE_SEC = 5 * 60;
export const LULD_AUCTION_SEC = 5 * 60;
export const LULD_CONFIDENT_WINDOW_SEC = LULD_PAUSE_SEC + LULD_AUCTION_SEC;
export const HALT_LATE_START_SKEW_SEC = 15;

export const HALT_KIND_LULD = 'luld';
export const HALT_KIND_REGULATORY = 'regulatory';
export const HALT_KIND_UNKNOWN = 'unknown';

export const HALT_BADGE_LULD = 'LULD';
export const HALT_BADGE_NEWS = 'NEWS';
export const HALT_BADGE_UNK = 'UNK';

export const HALT_LABEL_EXTENDED = 'Extended · no ETA';
export const HALT_LABEL_STILL = HALT_LABEL_EXTENDED;
export const HALT_LABEL_REGULATORY = 'NEWS · HALTED';
export const HALT_LABEL_UNKNOWN = 'UNK · HALTED';

export const HALT_RULE_LULD =
  'halt_start + 5m LULD pause, then ~5m auction. After 10m still halted: no confident countdown (further +5m auction windows possible).';
export const HALT_RULE_REGULATORY = 'News / regulatory halt -- no timed reopen estimate.';
export const HALT_RULE_UNKNOWN = 'Halt signaled; type unknown -- no timed reopen estimate.';

export const HALT_TYPE_LULD = 'LULD / volatility pause';
export const HALT_TYPE_REGULATORY = 'News / regulatory';
export const HALT_TYPE_UNKNOWN = 'Unknown';

export const HALT_START_OBSERVED_NOTE =
  'observed first ticker.halted (incoming tick type 49) -- not the SIP official start';
export const HALT_START_LATE_NOTE =
  'halt_start observed late (reconnect or opened mid-halt) -- elapsed only, no confident reopen ETA';
export const HALT_EXCHANGE_PENDING_NOTE =
  'Exchange detail pending -- Nasdaq Trade Halt RSS unmatched or unavailable. Resume times are not invented.';

export const HALT_DESK_POLL_MS = 5_000;
export const MWCB_BANNER_SOURCE = 'nasdaq_trade_halt_rss';
