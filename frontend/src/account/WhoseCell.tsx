/**
 * Whose a row is (ADR 072, mockup three-books v1 section 6): one chip in the book's colour -- You, Claude, The
 * brain, or Earlier bots with the retired bot's name ("Earlier bots · Live Trader"). A trade you closed after its
 * trader handed it to you reads "The brain · closed by you" (its P&L stays on that trader's record); a switched-off
 * trader's open position, handed to you, reads "The brain's · yours to close", dashed. One of Nova's own closes
 * (no owner) reads "Nova". There is no Close on another trader's row: you switch the trader off (ADR 072). The
 * Account page and every other positions list draw the same chip.
 */
import {
  OWNER_NAMES,
  ownerBotName,
  ownerClosedByYou,
  ownerYoursToClose,
  type Owner,
} from '../constantGroups/owners';
import { whoName } from './ownerView';
import './whose.css';

export interface WhoseTag {
  owner: Owner | null | undefined;
  bot?: string | null;
  /** An open position a switched-off trader (or a retired bot) handed you. */
  handed?: boolean;
  /** A trade you closed after its trader handed it to you. */
  closedByYou?: boolean;
}

interface ChipProps extends WhoseTag {
  /** Kept for the desk's lists; the chip is the mockup's pill everywhere. */
  pill?: boolean;
}

/** The chip's words: the book's name, then what follows its " · " (null for none). */
export function whoseWords({ owner, bot, handed, closedByYou }: WhoseTag): { main: string; sub: string | null; by: boolean } {
  const split = (text: string, by: boolean) => {
    const at = text.indexOf(' · ');
    return at < 0 ? { main: text, sub: null, by } : { main: text.slice(0, at), sub: text.slice(at + 3), by };
  };
  if (!owner) return { main: whoName(null, null), sub: null, by: false };
  if (owner !== 'you' && closedByYou) return split(ownerClosedByYou(owner), true);
  if (owner !== 'you' && handed) return split(ownerYoursToClose(owner), false);
  if (owner === 'earlier_bots' && bot) return { main: OWNER_NAMES.earlier_bots, sub: ownerBotName(bot), by: false };
  return { main: OWNER_NAMES[owner], sub: null, by: false };
}

export function WhoseChip({ owner, bot = null, pill = false, handed = false, closedByYou = false }: ChipProps) {
  const words = whoseWords({ owner, bot, handed, closedByYou });
  const isHanded = handed && !closedByYou && owner != null && owner !== 'you';
  const cls = `acct-who is-${owner ?? 'nova'}${isHanded ? ' is-handed' : ''}${pill ? ' is-pill' : ''}`;
  return (
    <span className={cls} data-testid="account-whose" data-owner={owner ?? 'nova'}>
      {words.main}
      {words.sub && <em className={words.by ? 'is-by' : undefined}>{` · ${words.sub}`}</em>}
    </span>
  );
}

/** Every holder a row touched (a fill that split across books), one chip each. */
export function WhoseChips({ tags }: { tags: readonly WhoseTag[] }) {
  return (
    <span className="acct-whose-chips">
      {tags.map((t) => <WhoseChip key={`${t.owner ?? 'nova'}-${t.bot ?? ''}-${t.closedByYou ? 'by' : ''}`} {...t} />)}
    </span>
  );
}
