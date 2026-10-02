/**
 * A pane whose line is lent to one of Nova's setups (ADR 043 decision 6): what it shows, and when
 * it asks for the line again.
 *
 * The backend sends `{type: "lent", ...}` and closes the socket. The pane then never reconnects by
 * its backoff: it waits on the shared lines poll (loanWatch) and asks again once no loan names its
 * symbol -- or at once when it comes to the front (on screen, with the document visible), which
 * opens the socket with `front=1` and recalls the loan. The lent words stay up until that socket
 * answers (subscribed, data or an error); one that closes unanswered hands over to the backoff.
 * useIbkrDepth and useIbkrTape each keep one, so a Trader tab's Level 2 and Time & Sales -- lent
 * together -- come back together.
 */
import { lentFromFrame, lentFromLoan, type LineLent } from './lentWords';
import { watchLoan } from './loanWatch';

/** The document is shown (not a minimised or covered window): with the pane on screen, it is in front. */
export function documentVisible(): boolean {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden';
}

export interface LentLineHooks {
  /** The pane is on screen and the document visible: a socket it opens recalls the loan. */
  inFront(): boolean;
  /** Open the socket again now (it says `front=1` while in front). */
  reconnect(): void;
  /** The lent words changed (the poll's newer reason): show them. */
  changed(): void;
}

export class LentLine {
  private lentNow: LineLent | null = null;
  // The socket asking for the line back is open: the lent words stay until it answers.
  private takingBack = false;
  private unwatch: (() => void) | null = null;
  private readonly onVisibility = (): void => this.wake();
  private readonly symbol: string;
  private readonly hooks: LentLineHooks;

  constructor(symbol: string, hooks: LentLineHooks) {
    this.symbol = symbol.toUpperCase();
    this.hooks = hooks;
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', this.onVisibility);
  }

  /** The words to show while the line is lent; null while the pane has its line. */
  get lent(): LineLent | null {
    return this.lentNow;
  }

  /** The socket read the lent frame: the line is gone until the loan ends (the socket closes next). */
  lend(msg: Record<string, unknown>): void {
    this.takingBack = false;
    this.lentNow = lentFromFrame(msg);
  }

  /** The socket that asked for the line back answered: it is this pane's again, or it says why not. */
  answered(): void {
    if (!this.lentNow) return;
    this.takingBack = false;
    this.lentNow = null;
    this.stopWatch();
  }

  /**
   * The socket closed. True when the lent line takes it from here -- it waits on the poll, or asks
   * again at once from the front -- so the pane must not reconnect by its backoff. False when the
   * line was not lent, or the socket that asked for it back closed unanswered: the backoff decides.
   */
  closed(): boolean {
    if (!this.lentNow) return false;
    if (this.takingBack) {
      this.takingBack = false;
      this.lentNow = null;
      return false;
    }
    if (this.hooks.inFront()) this.takeBack();
    else this.watch();
    return true;
  }

  /** The pane came to the front (shown, or the document became visible): a lent line is asked back now. */
  wake(): void {
    if (this.lentNow && this.hooks.inFront()) this.takeBack();
  }

  dispose(): void {
    if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', this.onVisibility);
    this.stopWatch();
    this.lentNow = null;
    this.takingBack = false;
  }

  private takeBack(): void {
    if (!this.lentNow || this.takingBack) return;
    this.takingBack = true;
    this.stopWatch();
    this.hooks.reconnect();
  }

  private watch(): void {
    if (this.unwatch) return;
    this.unwatch = watchLoan(this.symbol, {
      standing: (loan) => {
        if (!this.lentNow || this.takingBack) return;
        this.lentNow = lentFromLoan(loan);
        this.hooks.changed();
      },
      ended: () => this.takeBack(),
    });
  }

  private stopWatch(): void {
    this.unwatch?.();
    this.unwatch = null;
  }
}
