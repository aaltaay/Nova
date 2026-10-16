/** The capacity strip's read (architecture/schema/desk-ops.md, "IBKR capacity on the desk"). */
export const CAPACITY_PATH = '/api/ibkr/capacity';
export const CAPACITY_POLL_MS = 5_000;
export const CAPACITY_READ_TIMEOUT_MS = 4_000;
/** A cap at or under this many slots draws one box per slot; above it, one bar. */
export const CAPACITY_BOXES_MAX = 12;
