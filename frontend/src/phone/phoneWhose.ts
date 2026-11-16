/**
 * Whose a phone row is (ADR 072, mockup three-books v1 "Phone › Account"): you, Claude, the brain, or Earlier bots,
 * and whether the shares are handed to you. Pure. Every word is the desk's own (`constantGroups/owners`); only the
 * short chip is the phone's.
 */
import type { AccountPosition } from '../account/accountPositions';
import type { HistoryFill } from '../account/accountHistoryTypes';
import type { AccountFillRow } from '../account/accountLive';
import { practiceFillRows } from '../account/accountLive';
import {
  OWNER_HANDED,
  OWNER_NAMES,
  OWNER_NOVA_NAME,
  OWNER_SHORT_LABELS,
  OWNERS,
  ownerBotName,
  ownerClosedByYou,
  ownerYoursToClose,
  type Owner,
} from '../constantGroups/owners';
import type { PracticePosition } from '../practice/practiceTypes';

/** Whose a row is. `owner` null: one of Nova's own closes. `handed`: the trader's shares, yours to close. */
export interface Whose {
  owner: Owner | null;
  bot: string | null;
  handed: boolean;
  /** A fill you sent that closed shares handed to you: booked on `owner`'s record. */
  closedByYou: boolean;
}

/** A position row and whose it is; `whose` null when the wire did not say (Live, an older backend). */
export type PhonePosition = AccountPosition & { whose: Whose | null };
/** A fill row and whose order it was; `whose` null when the wire did not say (Live). */
export type PhoneFillRow = AccountFillRow & { whose: Whose | null };

/** The wire's `owner` as one of the four books, or null for anything else (a retired name, nothing). */
export function ownerOf(value: string | null | undefined): Owner | null {
  return OWNERS.find((o) => o === value) ?? null;
}

/** The words on a who-chip and its title: "Claude", "Earlier", "Handed" (the trader's colour), "Nova". */
export function whoChip(whose: Whose): { text: string; title: string } {
  const owner = whose.owner;
  if (!owner) return { text: OWNER_NOVA_NAME, title: OWNER_NOVA_NAME };
  const name = owner === 'earlier_bots' && whose.bot ? ownerBotName(whose.bot) : OWNER_NAMES[owner];
  if (whose.closedByYou) return { text: OWNER_HANDED, title: ownerClosedByYou(owner) };
  if (whose.handed) return { text: OWNER_HANDED, title: ownerYoursToClose(owner) };
  return { text: OWNER_SHORT_LABELS[owner], title: name };
}

/** Whose one position row is, with the ledger's `handed` for that holder; null when the row names no book. */
export function positionWhose(
  row: Pick<AccountPosition, 'symbol' | 'owner' | 'bot'>,
  ledger: readonly PracticePosition[],
): Whose | null {
  const owner = ownerOf(row.owner);
  if (!owner) return null;
  const bot = row.bot ?? null;
  const holder = ledger
    .find((p) => p.symbol.toUpperCase() === row.symbol)
    ?.by_owner?.find((h) => h.owner === owner && (h.bot ?? null) === bot);
  return { owner, bot, handed: holder?.handed === true, closedByYou: false };
}

/**
 * Whose a fill was: the order's book; or, when your close took shares a trader handed to you, that trader's
 * (its record keeps the P&L). Null when the fill names no book (an older ledger).
 */
export function fillWhose(fill: HistoryFill): Whose | null {
  const taken = (fill.parts ?? []).find((p) => p.closed_by === 'you' && p.owner !== 'you');
  if (taken) return { owner: taken.owner, bot: taken.bot ?? null, handed: true, closedByYou: true };
  if (fill.owner === undefined) return null;
  return { owner: ownerOf(fill.owner), bot: fill.bot ?? null, handed: false, closedByYou: false };
}

/** Whose a working order is: the order's book (null: one of Nova's own closes); null when the wire did not say. */
export function orderWhose(order: { owner?: string | null; bot?: string | null }): Whose | null {
  if (order.owner === undefined) return null;
  return { owner: ownerOf(order.owner), bot: order.bot ?? null, handed: false, closedByYou: false };
}

/** The ledger's fills as the Fills tab's rows, newest first, each saying whose it was. */
export function whoseFillRows(fills: readonly HistoryFill[]): PhoneFillRow[] {
  return fills
    .map((fill, i): PhoneFillRow => ({ ...practiceFillRows([fill])[0], key: `practice-${fill.order_id}-${fill.ts}-${i}`, whose: fillWhose(fill) }))
    .sort((a, b) => (b.ts ?? 0) - (a.ts ?? 0));
}
