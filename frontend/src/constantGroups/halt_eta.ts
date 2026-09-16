/** LULD / halt ETA chip copy and clock windows (mirrors backend halt_eta). */

export const LULD_PAUSE_SEC = 5 * 60;
export const LULD_AUCTION_SEC = 5 * 60;
export const LULD_CONFIDENT_WINDOW_SEC = LULD_PAUSE_SEC + LULD_AUCTION_SEC;

export const HALT_KIND_LULD = 'luld';
export const HALT_KIND_REGULATORY = 'regulatory';
export const HALT_KIND_UNKNOWN = 'unknown';

export const HALT_LABEL_STILL = 'Still halted · auction extended';
export const HALT_LABEL_REGULATORY = 'HALTED · news/regulatory';
export const HALT_LABEL_UNKNOWN = 'HALTED · ETA unknown';

export const HALT_RULE_LULD =
  'halt_start + 5m LULD pause, then ~5m auction. After 10m still halted: no confident countdown (further +5m auction windows possible).';
export const HALT_RULE_REGULATORY = 'News / regulatory halt -- no timed reopen estimate.';
export const HALT_RULE_UNKNOWN = 'Halt signaled; type unknown -- no timed reopen estimate.';

export const HALT_TYPE_LULD = 'LULD / volatility pause';
export const HALT_TYPE_REGULATORY = 'News / regulatory';
export const HALT_TYPE_UNKNOWN = 'Unknown';

export const HALT_START_OBSERVED_NOTE =
  'observed; first IBKR tick 49 -- not the SIP official start';
