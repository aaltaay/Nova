/**
 * Tells a socket that went quiet from a market that went quiet (operator report 2026-11-17: on the phone "the time
 * and sale was not moving ... there was a missing piece").
 *
 * The backend never leaves a Level 2 or Time & Sales socket silent: the tape says something at least every second
 * (a print, or a `ping`), Level 2 every 250 ms (a book, or a `beat`). So a socket that has said nothing for
 * LINK_QUIET_MS is not a quiet stock: the link under it is gone, and a browser can take minutes to notice (a phone
 * that changed network, a tunnel that re-routed). The watch says so once per socket (`quiet`), and its owner drops
 * the socket and asks again. A socket that never said anything is given LINK_OPEN_MS: the backend may be asking
 * IBKR for the line.
 *
 * Only while the page is in front: a hidden page's timers and sockets are the browser's to pause. A page coming
 * back gives its socket LINK_WAKE_GRACE_MS to speak before it is judged, and tells its owner (`woke`), which makes
 * a reconnect that was waiting on its backoff at once. The same on the browser's `online`.
 *
 * Every moment is the desk's clock (`deskNow`), the one the view registry judges on.
 */
import { LINK_OPEN_MS, LINK_QUIET_MS, LINK_WAKE_GRACE_MS, LINK_WATCH_TICK_MS } from '../constantGroups/market_view';
import { deskNow } from '../utils/deskClock';

export interface SocketWatchHooks {
  /** The socket has said nothing since `since` (desk clock, ms): told once per socket. */
  quiet(since: number): void;
  /** The page came back to the front, or the browser came back online. */
  woke?(): void;
}

function pageVisible(): boolean {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden';
}

export class SocketWatch {
  private last = 0;
  private spoke = false;
  private told = false;
  private live = false;
  private timer: ReturnType<typeof setInterval> | null = null;
  private readonly hooks: SocketWatchHooks;
  private readonly onVisibility = (): void => {
    if (pageVisible()) this.wake();
  };
  private readonly onOnline = (): void => this.wake();

  constructor(hooks: SocketWatchHooks) {
    this.hooks = hooks;
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', this.onVisibility);
    if (typeof window !== 'undefined') window.addEventListener('online', this.onOnline);
  }

  /** A socket was just asked for. */
  opened(now = deskNow()): void {
    this.live = true;
    this.spoke = false;
    this.told = false;
    this.last = now;
    if (this.timer == null) this.timer = setInterval(() => this.check(), LINK_WATCH_TICK_MS);
  }

  /** The socket said something: any frame at all. */
  heard(now = deskNow()): void {
    this.last = now;
    this.spoke = true;
    this.told = false;
  }

  /** The socket is gone (it closed, or its owner dropped it). */
  closed(): void {
    this.live = false;
    this.stop();
  }

  dispose(): void {
    this.closed();
    if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', this.onVisibility);
    if (typeof window !== 'undefined') window.removeEventListener('online', this.onOnline);
  }

  /** Judge the socket now (the timer's tick; tests). */
  check(now = deskNow()): void {
    if (!this.live || this.told || !pageVisible()) return;
    if (now - this.last <= (this.spoke ? LINK_QUIET_MS : LINK_OPEN_MS)) return;
    this.told = true;
    this.hooks.quiet(this.last);
  }

  private wake(now = deskNow()): void {
    if (this.live && !this.told) {
      // What the socket missed while the page slept is not its silence: it gets a moment to speak.
      const limit = this.spoke ? LINK_QUIET_MS : LINK_OPEN_MS;
      this.last = Math.max(this.last, now - limit + LINK_WAKE_GRACE_MS);
    }
    this.hooks.woke?.();
  }

  private stop(): void {
    if (this.timer != null) clearInterval(this.timer);
    this.timer = null;
  }
}
