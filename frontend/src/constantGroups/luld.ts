/** LULD bands on Level 2 (ADR 047): Nova's calculation from the published Limit Up-Limit Down rules. */

/** The `luld` frame's shape (backend `luld/views.py`); an unknown version is ignored. */
export const LULD_SCHEMA_VERSION = 1;
/** The band rows and the strip: red, a hard limit -- never the bid / ask green or red of the book. */
export const LULD_COLOR = '#f43f5e';
/** A limit state's countdown redraws this often. */
export const LULD_TICK_MS = 250;
/** The strip's word for the band. */
export const LULD_LABEL = 'LULD';
/** An approximate band's mark (Nova did not see the stock open or reopen). */
export const LULD_APPROX_MARK = '≈';
/** The hover's title. */
export const LULD_TIP_TITLE = 'Limit up / limit down (LULD)';
