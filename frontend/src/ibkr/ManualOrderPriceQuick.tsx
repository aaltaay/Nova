/**
 * Bid / Mid / Ask beside the compact ticket's price input. A click sets the
 * limit from the live top of book and keeps it there as Level 2 moves; the
 * lit button is the side being followed, and clicking it again stops (the
 * price stays). Without a book for this symbol the buttons grey out and say
 * so -- last trade is never substituted.
 */
import {
  TICKET_PRICE_ASK,
  TICKET_PRICE_BID,
  TICKET_PRICE_FOLLOW_HOLDING,
  TICKET_PRICE_FOLLOW_STOP,
  TICKET_PRICE_FOLLOWING_TITLE,
  TICKET_PRICE_MID,
  TICKET_PRICE_QUICK_ARIA,
  TICKET_PRICE_QUICK_NO_BOOK,
  TICKET_PRICE_QUICK_TITLE,
} from '../constantGroups/trader_chrome';
import type { TopOfBookLike } from './applyTicketDefaults';
import {
  QUICK_PRICE_KINDS,
  quickPriceFromBook,
  type QuickPriceKind,
} from './ticketPriceQuick';

const LABELS: Record<QuickPriceKind, string> = {
  bid: TICKET_PRICE_BID,
  mid: TICKET_PRICE_MID,
  ask: TICKET_PRICE_ASK,
};

interface Props {
  symbol: string;
  /** The desk's live top of book (the ticket already reads TopOfBookContext). */
  book: TopOfBookLike | null;
  /** The side the limit follows; null once the operator typed their own price. */
  following: QuickPriceKind | null;
  disabled: boolean;
  /** Why `disabled` is set -- each locked button says it (ux/whyTip.ts). */
  why?: string | null;
  /** `kind` null stops following and leaves the price where it is. */
  onFollow: (kind: QuickPriceKind | null, price: string | null) => void;
}

/** Why a button is locked with no book for this symbol (ux/whyTip.ts). */
function noBookWhy(following: boolean): string {
  return following ? `${TICKET_PRICE_QUICK_NO_BOOK}; ${TICKET_PRICE_FOLLOW_HOLDING}` : TICKET_PRICE_QUICK_NO_BOOK;
}

function buttonTitle(kind: QuickPriceKind, price: string, following: boolean): string {
  return following
    ? `${TICKET_PRICE_FOLLOWING_TITLE} ${kind}: ${price} -- ${TICKET_PRICE_FOLLOW_STOP}`
    : `${TICKET_PRICE_QUICK_TITLE} ${kind}: ${price}`;
}

export function ManualOrderPriceQuick({ symbol, book, following, disabled, why = null, onFollow }: Props) {
  return (
    <div
      className="mot-mini"
      role="group"
      aria-label={TICKET_PRICE_QUICK_ARIA}
      data-testid="manual-order-price-quick"
    >
      {QUICK_PRICE_KINDS.map((kind) => {
        const price = quickPriceFromBook(kind, book, symbol);
        const active = following === kind;
        // No book outlives the ticket's own lock, so it answers first.
        const lockWhy = price == null ? noBookWhy(active) : disabled ? why || undefined : undefined;
        return (
          <button
            key={kind}
            type="button"
            className={active ? 'is-on' : ''}
            aria-pressed={active}
            disabled={disabled || price == null}
            title={price == null || lockWhy ? undefined : buttonTitle(kind, price, active)}
            data-why={lockWhy}
            data-testid={`manual-order-price-${kind}`}
            onClick={() => {
              if (active) onFollow(null, null);
              else if (price != null) onFollow(kind, price);
            }}
          >
            {LABELS[kind]}
          </button>
        );
      })}
    </div>
  );
}
