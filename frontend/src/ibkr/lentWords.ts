/**
 * What a lent line says (ADR 044 decision 6): whose setup took it, why, and when it comes back.
 *
 * A Trader tab's Level 2 and Time & Sales lines go to one of Nova's setups together, and each
 * pane says so in its own sentence, built from the desk's own words: the lent frame and the lines
 * poll carry the fields, and the backend's own sentence (`text`) is kept but not shown. A frame
 * that names no borrower still says the line is lent and when it comes back; nothing is invented.
 * A line lent to Claude's seat (ADR 068 decision 14) says what Claude does there, and that only the operator's
 * right-click on the tab, or Claude letting it go, brings it back.
 */
import { BOT_SETUP_LABELS } from '../constantGroups/bot';
import {
  L2_LENT_BACK,
  L2_LENT_CLAUDE,
  L2_LENT_CLAUDE_BACK,
  L2_LENT_CLAUDE_WHY_WORDS,
  L2_LENT_PREFIX,
  L2_LENT_SOMEONE,
  L2_LENT_WHY_WORDS,
  TAPE_LENT_CLAUDE_BACK,
  TAPE_LENT_PREFIX,
} from '../constantGroups/market_ui';
import type { DepthLoan } from './depthLines';

/** Who took the line and why -- what the lent frame and the lines poll say. */
export interface LentTo {
  /** The borrower's symbol. */
  symbol: string | null;
  setupType: string | null;
  /** trade | near | armed (the loan's reason now). */
  tier: string | null;
  /** The backend's words for the reason, when it sends no tier the desk knows. */
  why: string | null;
}

/** A pane's line is lent: who took it, since when, and the backend's own sentence. */
export interface LineLent extends LentTo {
  since: number | null;
  /** The backend's sentence (each pane builds its own from the fields above). */
  text: string | null;
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v ? v : null;
}

/** The `{type: "lent", ...}` frame a lent socket reads before it closes. */
export function lentFromFrame(msg: Record<string, unknown>): LineLent {
  const to = (msg.to != null && typeof msg.to === 'object' ? msg.to : {}) as Record<string, unknown>;
  return {
    symbol: str(to.symbol)?.toUpperCase() ?? null,
    setupType: str(to.setup_type),
    tier: str(msg.tier),
    why: str(msg.why),
    since: typeof msg.since === 'number' ? msg.since : null,
    text: str(msg.text),
  };
}

/** The poll's word on a standing loan: its reason moves (armed, then near, then a trade). */
export function lentFromLoan(loan: DepthLoan): LineLent {
  return {
    symbol: loan.borrower, setupType: loan.setup_type, tier: loan.tier, why: loan.why, since: loan.since,
    text: loan.text,
  };
}

/** The line went to Claude's seat, not to a setup: only the operator's right-click brings it back. */
export function lentToClaude(to: LentTo | null | undefined): boolean {
  return to?.setupType === L2_LENT_CLAUDE;
}

/** "Claude (watching RUNR)" -- from the tier and the stock, else the backend's own words. */
function claudeWho(to: LentTo): string {
  const words = to.tier ? L2_LENT_CLAUDE_WHY_WORDS[to.tier] : undefined;
  const why = words && to.symbol ? `${words} ${to.symbol}` : to.why;
  return why ? `Claude (${why})` : 'Claude';
}

/**
 * "<prefix> AISP's first pullback (near its trigger) — back when it ends or when you bring this
 * tab to the front".
 */
export function lentText(prefix: string, to: LentTo): string {
  if (lentToClaude(to)) {
    return `${prefix} ${claudeWho(to)} — ${prefix === TAPE_LENT_PREFIX ? TAPE_LENT_CLAUDE_BACK : L2_LENT_CLAUDE_BACK}`;
  }
  const label = to.setupType ? (BOT_SETUP_LABELS[to.setupType] ?? to.setupType.replace(/_/g, ' ')) : null;
  const who = to.symbol ? `${to.symbol}'s ${(label ?? 'setup').toLowerCase()}` : L2_LENT_SOMEONE;
  const why = (to.tier ? L2_LENT_WHY_WORDS[to.tier] : null) ?? to.why;
  return `${prefix} ${who}${to.symbol && why ? ` (${why})` : ''} — ${L2_LENT_BACK}`;
}

/** The ladder's sentence: "Level 2 lent to ...". */
export function depthLentText(to: LentTo): string {
  return lentText(L2_LENT_PREFIX, to);
}

/** Time & Sales' sentence: "Time & Sales lent to ...". */
export function tapeLentText(to: LentTo): string {
  return lentText(TAPE_LENT_PREFIX, to);
}
