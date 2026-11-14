/**
 * Whose trades the Account page shows (ADR 072): All, You, Claude, the brain, or Earlier bots (one retired bot when
 * picked). Pure.
 *
 * `viewHistory` narrows a history to one book, or one retired bot, from the stamps the backend already split
 * (architecture/schema/recording-and-replay.md, "Three traders' books"): each fill becomes its parts for that book
 * (dropped when it has none), each day its book's sums, each equity point that book's running P&L. All, and a
 * history with no parts (an older backend), pass through unchanged -- so every panel draws the view with the code it
 * already has.
 */
import {
  OWNER_NAMES,
  OWNER_NOVA_NAME,
  OWNERS,
  ownerBotName,
  type Owner,
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
  /** One retired bot inside Earlier bots (its origin), or null for all of them. */
  bot: string | null;
}

/** The page opens on All every time (the operator, 2026-11-03). */
export const ALL_VIEW: OwnerView = { book: 'all', bot: null };

/** "You", "Claude", "The brain", the retired bot's name, or "Nova" for one of Nova's own closes. */
export function whoName(owner: HistoryOwner | null | undefined, bot: string | null | undefined): string {
  if (owner === 'earlier_bots') return ownerBotName(bot);
  if (owner && owner in OWNER_NAMES) return OWNER_NAMES[owner];
  return OWNER_NOVA_NAME;
}

/** True when `view` shows a holder. */
export function shows(view: OwnerView, owner: HistoryOwner | null | undefined, bot: string | null | undefined): boolean {
  if (view.book === 'all') return true;
  if (owner !== view.book) return false;
  return view.book !== 'earlier_bots' || view.bot == null || bot === view.bot;
}

/** The retired bots that ever traded in `history`, first-fill order. */
export function botsOf(history: PracticeHistory | null): string[] {
  const out: string[] = [];
  for (const row of history?.by_owner ?? []) {
    if (row.owner === 'earlier_bots' && row.bot && !out.includes(row.bot)) out.push(row.bot);
  }
  return out;
}

const splits = (history: PracticeHistory): boolean => history.fills.some((f) => Array.isArray(f.parts));

function daySums(row: HistoryDaily, view: OwnerView): HistoryBookSums | null {
  if (view.book === 'all') return null;
  if (view.book === 'earlier_bots' && view.bot) return row.by_bot?.[view.bot] ?? null;
  return row[view.book] ?? null;
}

function viewFill(fill: HistoryFill, view: OwnerView): HistoryFill | null {
  const parts = (fill.parts ?? []).filter((p) => shows(view, p.owner, p.bot));
  if (!parts.length) return null;
  const sum = (key: 'qty' | 'realized' | 'commission' | 'fees'): number => parts.reduce((s, p) => s + p[key], 0);
  return { ...fill, qty: sum('qty'), realized: sum('realized'), commission: sum('commission'), fees: sum('fees'), parts };
}

function pointFigures(p: EquityPoint, view: OwnerView): { pnl: number; realized: number } {
  if (view.book === 'earlier_bots' && view.bot) {
    return { pnl: p.by_bot?.[view.bot] ?? 0, realized: p.by_bot_realized?.[view.bot] ?? 0 };
  }
  const book = view.book as Owner;
  return { pnl: p[`${book}_pnl`] ?? 0, realized: p[`${book}_realized`] ?? 0 };
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
    bot_realized: view.book === 'you' ? 0 : realized,
  };
  const by_owner = (history.by_owner ?? []).filter((r) => shows(view, r.owner, r.bot));
  const by_source = history.by_source.filter(() => false);
  return { ...history, fills, daily, equity, components, by_owner, by_source };
}

/** Each book's realized on one day (or over a month). */
export type DaySplit = Record<Owner, number>;

export const emptySplit = (): DaySplit => ({ you: 0, claude: 0, brain: 0, earlier_bots: 0 });

/** The books that traded in `split` (a non-zero figure), in the order every split reads them. */
export const tradedIn = (split: DaySplit | null | undefined): Owner[] =>
  split ? OWNERS.filter((o) => Math.abs(split[o]) >= 0.005) : [];

/** Each date's realized per book (archived rows included), for the calendar's All view; null with no split. */
export function daySplits(history: PracticeHistory | null): Map<string, DaySplit> | null {
  if (!history || !history.daily.some((row) => OWNERS.some((o) => row[o]))) return null;
  const out = new Map<string, DaySplit>();
  for (const row of history.daily) {
    const day = out.get(row.date) ?? emptySplit();
    for (const owner of OWNERS) day[owner] += row[owner]?.realized ?? 0;
    out.set(row.date, day);
  }
  return out;
}

/** Each book's fills on one date, for the day card's "By trader" rows. */
export function dayFillCounts(history: PracticeHistory | null, date: string): DaySplit | null {
  const rows = (history?.daily ?? []).filter((row) => row.date === date);
  if (!rows.length || !rows.some((row) => OWNERS.some((o) => row[o]))) return null;
  const out = emptySplit();
  for (const row of rows) for (const owner of OWNERS) out[owner] += row[owner]?.fills ?? 0;
  return out;
}

/** Each book's realized over the dates that start with `prefix` (YYYY-MM): the book cards' month. */
export function monthSplit(splits: Map<string, DaySplit> | null, prefix: string): DaySplit | null {
  if (!splits) return null;
  const out = emptySplit();
  for (const [date, day] of splits) {
    if (!date.startsWith(prefix)) continue;
    for (const owner of OWNERS) out[owner] += day[owner];
  }
  return out;
}

/** The view's book on the account's day (`books` of /api/practice/account); null for All or no books. */
export function viewBookDay(books: PracticeBooks | null | undefined, view: OwnerView): PracticeBookDay | null {
  if (!books || view.book === 'all') return null;
  if (view.book === 'earlier_bots' && view.bot) return books.earlier_bots?.by_bot?.[view.bot] ?? null;
  return books[view.book] ?? null;
}
