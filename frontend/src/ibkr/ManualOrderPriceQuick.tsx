/**
 * Bid / Mid / Ask beside the compact ticket's price input. Each button sets
 * the limit from the live top of book; without a book for this symbol the
 * buttons grey out and say so -- last trade is never substituted.
 */
import {
  TICKET_PRICE_ASK,
  TICKET_PRICE_BID,
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
  /** Current price field text; the button whose price matches reads as selected. */
  value: string;
  disabled: boolean;
  onPick: (price: string) => void;
}

export function ManualOrderPriceQuick({ symbol, book, value, disabled, onPick }: Props) {
  return (
    <div
      className="mot-mini"
      role="group"
      aria-label={TICKET_PRICE_QUICK_ARIA}
      data-testid="manual-order-price-quick"
    >
      {QUICK_PRICE_KINDS.map((kind) => {
        const price = quickPriceFromBook(kind, book, symbol);
        const active = price != null && price === value;
        return (
          <button
            key={kind}
            type="button"
            className={active ? 'is-on' : ''}
            aria-pressed={active}
            disabled={disabled || price == null}
            title={price == null ? TICKET_PRICE_QUICK_NO_BOOK : `${TICKET_PRICE_QUICK_TITLE}: ${price}`}
            data-testid={`manual-order-price-${kind}`}
            onClick={() => {
              if (price != null) onPick(price);
            }}
          >
            {LABELS[kind]}
          </button>
        );
      })}
    </div>
  );
}
