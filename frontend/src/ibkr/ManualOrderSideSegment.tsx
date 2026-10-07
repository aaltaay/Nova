/**
 * The ticket's sides, following the position (ADR 048, #778 step 3): flat Buy / Short, long Buy / Sell with
 * Short off ("Nova never flips"), short Cover / Short more with Sell off. A side that cannot be pressed says
 * why on hover (`data-why`), and the line under the sides says what the order does to the position.
 */
import { TICKER_TRADE_LABEL_SIDE } from '../constants';
import type { SideButton } from './shortTicketModel';
import type { TicketSide } from './ticketSide';
import type { OrderExplainerKind } from './orderExplainerCopy';
import type { BindOrderExplainer } from './useOrderExplainer';

interface Props {
  buttons: SideButton[];
  ticketSide: TicketSide;
  disabled: boolean;
  /** Why the whole ticket is locked (no Gateway, an order in flight), or undefined. */
  why: string | undefined;
  /** What this order does to the position ("A short sale: ...", "You are short 416. Cover ..."), or null. */
  note: string | null;
  /** The Live lock's own words when Short is off for the venue, shown under the sides. */
  shortReason: string | null;
  explain: BindOrderExplainer;
  onTicketSideChange: (side: TicketSide) => void;
}

const PRESSED_CLASS: Record<SideButton['tone'], string> = {
  buy: 'is-buy', sell: 'is-sell', short: 'is-short', cover: 'is-cover',
};

export function ManualOrderSideSegment({
  buttons, ticketSide, disabled, why, note, shortReason, explain, onTicketSideChange,
}: Props) {
  const withShort = buttons.some((b) => b.side === 'short');
  return (
    <>
      <div
        className={`manual-order-segment manual-order-side${withShort ? ' manual-order-side--with-short' : ''}`}
        role="group"
        aria-label={TICKER_TRADE_LABEL_SIDE}
      >
        {buttons.map((b) => {
          const pressed = ticketSide === b.side;
          const blocked = Boolean(b.lock);
          const kind: OrderExplainerKind | null = b.side === 'buy' ? 'buy' : b.side === 'sell' ? 'sell' : null;
          return (
            <button
              key={b.side}
              type="button"
              className={pressed ? PRESSED_CLASS[b.tone] : ''}
              aria-pressed={pressed}
              {...(kind && !blocked ? explain(kind) : {})}
              onClick={() => {
                if (!blocked) onTicketSideChange(b.side);
              }}
              disabled={disabled || blocked}
              data-why={b.lock || why}
              data-testid={`manual-order-side-${b.side}`}
            >
              {b.label}
            </button>
          );
        })}
      </div>
      {withShort && shortReason && (
        <p className="manual-order-hint mot-reason" data-testid="manual-order-short-reason">
          {shortReason}
        </p>
      )}
      {note && (
        <p className={`manual-order-hint mot-side-note${ticketSide === 'short' ? ' is-short' : ''}`}
          data-testid="manual-order-side-note">
          {note}
        </p>
      )}
    </>
  );
}
