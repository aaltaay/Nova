/**
 * One poll of `GET /api/ibkr/depth/lines` for every lent line in this window (ADR 044 decision 6).
 *
 * A pane whose line is lent to one of Nova's setups waits for the loan to end instead of
 * reconnecting by its backoff (lentLine.ts). A Trader tab's Level 2 and Time & Sales go to the
 * same loan, so every lent pane shares this poll: every L2_LENT_POLL_MS, one request answers each
 * watcher -- the loan that still names its symbol (its reason moves: armed, near, in a trade), or
 * that none does any more. An answer that cannot be read ends nothing: the lines stay lent, the
 * next poll asks again, and the first failure of a run is logged with its reason. A backend
 * without the route lends nothing, so no loan stands. The poll runs only while a pane waits.
 */
import { L2_LENT_POLL_MS } from '../constantGroups/market_ui';
import { loanFor, readLines, type DepthLoan } from './depthLines';

export interface LoanWatcher {
  /** The loan still stands: its newest word. */
  standing(loan: DepthLoan): void;
  /** No loan names the symbol any more: the pane asks for its line again. */
  ended(): void;
}

interface Entry {
  symbol: string;
  watcher: LoanWatcher;
}

const entries = new Map<number, Entry>();
let nextId = 1;
let timer: ReturnType<typeof setInterval> | null = null;
let inFlight: AbortController | null = null;
let failing = false;

/** Wait on the poll for ``symbol``'s loan; the returned function stops waiting. */
export function watchLoan(symbol: string, watcher: LoanWatcher): () => void {
  const id = nextId++;
  entries.set(id, { symbol: symbol.toUpperCase(), watcher });
  if (timer == null) timer = setInterval(() => void pollOnce(), L2_LENT_POLL_MS);
  return () => {
    if (entries.delete(id) && entries.size === 0) stop();
  };
}

function stop(): void {
  if (timer != null) {
    clearInterval(timer);
    timer = null;
  }
  inFlight?.abort();
  inFlight = null;
}

function tell(entry: Entry, loan: DepthLoan | null): void {
  try {
    if (loan) entry.watcher.standing(loan);
    else entry.watcher.ended();
  } catch (err) {
    // One pane's trouble never keeps the others waiting: they still hear this answer.
    console.warn(`Level 2 lines: the lent ${entry.symbol} pane could not take the poll's answer`, err);
  }
}

async function pollOnce(): Promise<void> {
  if (inFlight != null || entries.size === 0) return;
  const ctrl = new AbortController();
  inFlight = ctrl;
  const got = await readLines(ctrl.signal);
  if (inFlight === ctrl) inFlight = null;
  if (ctrl.signal.aborted) return;
  if (got.kind === 'unknown') {
    if (!failing) console.warn(`Level 2 lines: the lent lines stay lent, the loans could not be read: ${got.error}`);
    failing = true;
    return;
  }
  failing = false;
  for (const [id, entry] of [...entries]) {
    if (!entries.has(id)) continue;          // an earlier pane's answer stopped this one waiting
    tell(entry, got.kind === 'view' ? loanFor(got.view, entry.symbol) : null);
  }
}

/** How many panes wait on the poll (tests). */
export function loanWatchersForTests(): number {
  return entries.size;
}

export function resetLoanWatchForTests(): void {
  entries.clear();
  stop();
  failing = false;
}
