/**
 * A pane on a stock no lane is on (ADR 071): what it shows, and when it asks for a line again.
 *
 * The backend sends one lane frame -- Level 2 `{type: "error", evicted: true, lane, message}`, Time & Sales
 * `{type: "lane", lane, message}` -- and closes the socket. The pane then never reconnects by its backoff, and
 * never by itself from the front: two windows in front, each asking for your lane, would pass it to and fro and
 * end each other's lines. It asks again when
 * - the operator brings it to the front (its tab shown, its document made visible) or clicks its words
 *   (LANE_BRING_EVENT): the socket opens with `front=1` and moves your lane here;
 * - the shared lanes poll finds a lane on its stock (Claude's or the bots' came to it): the socket opens with
 *   `front=0`, so your lane stays where it is.
 * The words stay up until that socket answers; one that closes unanswered hands over to the backoff.
 * useIbkrDepth and useIbkrTape each keep one, so a Trader tab's Level 2 and Time & Sales come back together.
 */
import { LANE_BRING_EVENT, LANE_WAIT_POLL_MS, laneWaitNone, laneWaitPlain, laneWaitYours } from '../constantGroups/market_ui';
import { lanesOn, readLanes, type LanesView } from './lanes';

/** The document is shown (not a minimised or covered window): with the pane on screen, it is in front. */
export function documentVisible(): boolean {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden';
}

/** What a waiting pane says: where your lane is, in the pane's own words. */
export interface LaneWaitWords {
  /** The stock your lane is on; null when it is on none. */
  you: string | null;
  /** The pane's words, with how to bring your lane (a click on them, or the tab to the front). */
  text: string;
  /** The same without the how, where a click does nothing: the order lock, the heat map, the phone. */
  plain: string;
}

export function laneWaitText(pane: string, symbol: string, you: string | null): string {
  return you ? laneWaitYours(pane, you, symbol) : laneWaitNone(pane, symbol);
}

function words(pane: string, symbol: string, you: string | null): LaneWaitWords {
  return { you, text: laneWaitText(pane, symbol, you), plain: laneWaitPlain(pane, you, symbol) };
}

/** Ask the waiting panes of ``symbol`` in this window for their lines now (a click on their words). */
export function bringLane(symbol: string): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(LANE_BRING_EVENT, { detail: { symbol: symbol.toUpperCase() } }));
}

export interface LaneWaitHooks {
  /** The pane is on screen and the document visible. */
  inFront(): boolean;
  /** Open the socket again now; `front` says whether it moves your lane here. */
  reconnect(front: boolean): void;
  /** The words changed (the poll saw your lane move): show them. */
  changed(): void;
}

function youOf(msg: Record<string, unknown>): string | null {
  const lane = msg.lane;
  const you = lane != null && typeof lane === 'object' ? (lane as Record<string, unknown>).you : null;
  return typeof you === 'string' && you ? you.toUpperCase() : null;
}

export class LaneWait {
  private waitingNow: LaneWaitWords | null = null;
  // The socket asking for the line again is open: the words stay until it answers.
  private asking = false;
  private unwatch: (() => void) | null = null;
  private readonly onVisibility = (): void => this.wake();
  private readonly onBring = (e: Event): void => {
    const sym = (e as CustomEvent<{ symbol?: string }>).detail?.symbol;
    if (typeof sym === 'string' && sym.toUpperCase() === this.symbol) this.bring();
  };
  private readonly symbol: string;
  private readonly pane: string;
  private readonly hooks: LaneWaitHooks;

  constructor(symbol: string, pane: string, hooks: LaneWaitHooks) {
    this.symbol = symbol.toUpperCase();
    this.pane = pane;
    this.hooks = hooks;
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', this.onVisibility);
    if (typeof window !== 'undefined') window.addEventListener(LANE_BRING_EVENT, this.onBring);
  }

  /** The words while the pane waits for a lane; null while it has its line. */
  get waiting(): LaneWaitWords | null {
    return this.waitingNow;
  }

  /** The socket read the lane frame: no lane is on this stock (the socket closes next). */
  wait(msg: Record<string, unknown>): void {
    this.asking = false;
    const you = youOf(msg);
    this.waitingNow = words(this.pane, this.symbol, you);
  }

  /** The socket that asked again answered: the line is here, or it says why not. */
  answered(): void {
    if (!this.waitingNow) return;
    this.asking = false;
    this.waitingNow = null;
    this.stopWatch();
  }

  /**
   * The socket closed. True when the wait takes it from here -- the pane must not reconnect by its backoff.
   * False when it was not waiting, or the socket that asked again closed unanswered: the backoff decides.
   */
  closed(): boolean {
    if (!this.waitingNow) return false;
    if (this.asking) {
      this.asking = false;
      this.waitingNow = null;
      return false;
    }
    this.watch();
    return true;
  }

  /** The pane came to the front (shown, or the document became visible): your lane comes here. */
  wake(): void {
    if (this.waitingNow && this.hooks.inFront()) this.ask(true);
  }

  /** The operator clicked the words: your lane comes here. */
  bring(): void {
    if (this.waitingNow) this.ask(true);
  }

  dispose(): void {
    if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', this.onVisibility);
    if (typeof window !== 'undefined') window.removeEventListener(LANE_BRING_EVENT, this.onBring);
    this.stopWatch();
    this.waitingNow = null;
    this.asking = false;
  }

  private ask(front: boolean): void {
    if (!this.waitingNow || this.asking) return;
    this.asking = true;
    this.stopWatch();
    this.hooks.reconnect(front);
  }

  private watch(): void {
    if (this.unwatch) return;
    this.unwatch = watchLanes(this.symbol, {
      standing: (view) => {
        if (!this.waitingNow || this.asking || view.you.symbol === this.waitingNow.you) return;
        this.waitingNow = words(this.pane, this.symbol, view.you.symbol);
        this.hooks.changed();
      },
      // Claude's or the bots' lane came to this stock: its lines are up, and your lane stays where it is.
      arrived: () => this.ask(false),
    });
  }

  private stopWatch(): void {
    this.unwatch?.();
    this.unwatch = null;
  }
}

// -- one poll of GET /api/ibkr/lanes for every waiting pane in this window --------------------------------

export interface LanesWatcher {
  /** Still no lane on the stock: the newest view (your lane may have moved). */
  standing(view: LanesView): void;
  /** A lane is on the stock now. */
  arrived(): void;
}

interface Entry {
  symbol: string;
  watcher: LanesWatcher;
}

const entries = new Map<number, Entry>();
let nextId = 1;
let timer: ReturnType<typeof setInterval> | null = null;
let inFlight: AbortController | null = null;
let failing = false;

/**
 * Wait on the poll for a lane on ``symbol``; the returned function stops waiting. Every LANE_WAIT_POLL_MS one
 * request answers each watcher. An answer that cannot be read moves nothing: the panes keep waiting, the next
 * poll asks again, and the first failure of a run is logged with its reason. The poll runs only while a pane waits.
 */
export function watchLanes(symbol: string, watcher: LanesWatcher): () => void {
  const id = nextId++;
  entries.set(id, { symbol: symbol.toUpperCase(), watcher });
  if (timer == null) timer = setInterval(() => void pollOnce(), LANE_WAIT_POLL_MS);
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

function tell(entry: Entry, view: LanesView): void {
  try {
    if (lanesOn(view, entry.symbol).length) entry.watcher.arrived();
    else entry.watcher.standing(view);
  } catch (err) {
    // One pane's trouble never keeps the others waiting: they still hear this answer.
    console.warn(`Lanes: the waiting ${entry.symbol} pane could not take the poll's answer`, err);
  }
}

async function pollOnce(): Promise<void> {
  if (inFlight != null || entries.size === 0) return;
  const ctrl = new AbortController();
  inFlight = ctrl;
  const got = await readLanes(ctrl.signal);
  if (inFlight === ctrl) inFlight = null;
  if (ctrl.signal.aborted) return;
  if (got.kind === 'unknown') {
    if (!failing) console.warn(`Lanes: the waiting panes keep waiting, the lanes could not be read: ${got.error}`);
    failing = true;
    return;
  }
  failing = false;
  for (const [id, entry] of [...entries]) {
    if (!entries.has(id)) continue;          // an earlier pane's answer stopped this one waiting
    tell(entry, got.view);
  }
}

/** How many panes wait on the poll (tests). */
export function laneWatchersForTests(): number {
  return entries.size;
}

export function resetLaneWatchForTests(): void {
  entries.clear();
  stop();
  failing = false;
}
