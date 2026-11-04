/**
 * Whose trades the Account page shows (ADR 069): All, You, or Bots (one bot when picked). Pure.
 *
 * `viewHistory` narrows a Paper history to one book, or one bot, from the stamps the backend already split
 * (architecture/schema/recording-and-replay.md, "Your book and the bots' book"): each fill becomes its parts
 * for that book (dropped when it has none), each day its book's sums, each equity point that book's running
 * P&L. All, and a history with no parts (Sim, an older backend), pass through unchanged -- so every panel
 * draws the view with the code it already has.
 */
import {
  OWNER_NOVA_NAME,
  OWNER_YOU_NAME,
  ownerBotName,
  type OwnerBook,
} from '../constantGroups/owners';
import type {
  EquityPoint,
  HistoryBookSums,
  HistoryComponents,
  HistoryDaily,
  HistoryFill,
  HistoryOwner,
  PracticeHistory,
} from './accountHistoryTypes';
import type { PracticeBookDay, PracticeBooks } from '../practice';

export interface OwnerView {
  book: OwnerBook;
  /** One bot inside the bots' book (its origin), or null for every bot. */
  bot: string | null;
}

/** The page opens on All every time (the operator, 2026-11-03). */
export const ALL_VIEW: OwnerView = { book: 'all', bot: null };

/** "You", the bot's name, or "Nova" for one of Nova's own closes. */
export function whoName(owner: HistoryOwner | null | undefined, bot: string | null | undefined): string {
  if (owner === 'you') return OWNER_YOU_NAME;
  if (owner === 'bots') return ownerBotName(bot);
  return OWNER_NOVA_NAME;
}

/** True when `view` shows a holder. */
export function shows(view: OwnerView, owner: HistoryOwner | null | undefined, bot: string | null | undefined): boolean {
  if (view.book === 'all') return true;
  if (view.book === 'you') return owner === 'you';
  return owner === 'bots' && (view.bot == null || bot === view.bot);
}

/** The bots that ever traded in `history`, first-fill order. */
export function botsOf(history: PracticeHistory | null): string[] {
  const out: string[] = [];
  for (const row of history?.by_owner ?? []) {
    if (row.owner === 'bots' && row.bot && !out.includes(row.bot)) out.push(row.bot);
  }
  return out;
}

const splits = (history: PracticeHistory): boolean => history.fills.some((f) => Array.isArray(f.parts));

function daySums(row: HistoryDaily, view: OwnerView): HistoryBookSums | null {
  if (view.book === 'you') return row.you ?? null;
  if (view.bot) return row.by_bot?.[view.bot] ?? null;
  return row.bots ?? null;
}

function viewFill(fill: HistoryFill, view: OwnerView): HistoryFill | null {
  const parts = (fill.parts ?? []).filter((p) => shows(view, p.owner, p.bot));
  if (!parts.length) return null;
  const sum = (key: 'qty' | 'realized' | 'commission' | 'fees'): number => parts.reduce((s, p) => s + p[key], 0);
  return { ...fill, qty: sum('qty'), realized: sum('realized'), commission: sum('commission'), fees: sum('fees'), parts };
}

function pointFigures(p: EquityPoint, view: OwnerView): { pnl: number; realized: number } {
  if (view.book === 'you') return { pnl: p.you_pnl ?? 0, realized: p.you_realized ?? 0 };
  if (view.bot) return { pnl: p.by_bot?.[view.bot] ?? 0, realized: p.by_bot_realized?.[view.bot] ?? 0 };
  return { pnl: p.bots_pnl ?? 0, realized: p.bots_realized ?? 0 };
}

/** `history` as `view` sees it; All (or a history with no split) unchanged. */
export function viewHistory(history: PracticeHistory | null, view: OwnerView): PracticeHistory | null {
  if (!history || view.book === 'all' || !splits(history)) return history;
  const fills = history.fills.map((f) => viewFill(f, view)).filter((f): f is HistoryFill => f != null);
  const daily = history.daily
    .map((row) => {
      const sums = daySums(row, view);
      return sums ? { ...row, ...sums } : null;
    })
    .filter((row): row is HistoryDaily => row != null && row.fills > 0);
  const equity = history.equity.map((p) => {
    const { pnl, realized } = pointFigures(p, view);
    return { ...p, net_liquidation: history.starting_cash + pnl, cash: history.starting_cash + realized,
             realized, unrealized: pnl - realized };
  });
  const realized = fills.reduce((s, f) => s + f.realized, 0);
  const last = equity[equity.length - 1];
  const components: HistoryComponents = {
    ...history.components,
    realized,
    unrealized: last ? last.unrealized : 0,
    commissions: fills.reduce((s, f) => s + f.commission, 0),
    sec_finra_fees: fills.reduce((s, f) => s + f.fees, 0),
    bot_realized: view.book === 'bots' ? realized : 0,
  };
  const by_owner = (history.by_owner ?? []).filter((r) => shows(view, r.owner, r.bot));
  const by_source = history.by_source.filter(() => false);
  return { ...history, fills, daily, equity, components, by_owner, by_source };
}

export interface DaySplit {
  you: number;
  bots: number;
}

/** Each date's yours and the bots' realized (archived rows included), for the calendar's All view; null with
 *  no split (Sim, an older backend). */
export function daySplits(history: PracticeHistory | null): Map<string, DaySplit> | null {
  if (!history || !history.daily.some((row) => row.you || row.bots)) return null;
  const out = new Map<string, DaySplit>();
  for (const row of history.daily) {
    const day = out.get(row.date) ?? { you: 0, bots: 0 };
    day.you += row.you?.realized ?? 0;
    day.bots += row.bots?.realized ?? 0;
    out.set(row.date, day);
  }
  return out;
}

/** Each book's realized over the dates that start with `prefix` (YYYY-MM): the book cards' month. */
export function monthSplit(splits: Map<string, DaySplit> | null, prefix: string): DaySplit | null {
  if (!splits) return null;
  const out = { you: 0, bots: 0 };
  for (const [date, day] of splits) {
    if (!date.startsWith(prefix)) continue;
    out.you += day.you;
    out.bots += day.bots;
  }
  return out;
}

/** The view's book on the account's day (`books` of /api/practice/account); null for All or no books. */
export function viewBookDay(books: PracticeBooks | null | undefined, view: OwnerView): PracticeBookDay | null {
  if (!books || view.book === 'all') return null;
  if (view.book === 'you') return books.you;
  return view.bot ? books.bots.by_bot[view.bot] ?? null : books.bots;
}
