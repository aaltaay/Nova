/**
 * Compact ticket fields (approved Trader redesign, 2026-09-21): segmented Buy /
 * Sell / Short and Limit / Market / Stop, price with Bid / Mid / Ask, the qty
 * row, Extended hours beside `Cost · BP after`. Same fields and test ids.
 */
import {
  TICKER_TRADE_DEFAULT_ORDER_TYPE,
  TICKER_TRADE_LABEL_ORDER_TYPE,
  TICKER_TRADE_LABEL_SIDE,
  TICKER_TRADE_LABEL_TRADING_HOURS,
} from '../constants';
import {
  TICKER_TRADE_LABEL_BUY,
  TICKER_TRADE_LABEL_SELL,
  TICKER_TRADE_LABEL_SHORT,
} from '../constantGroups/shortability';
import {
  TICKET_BP_AFTER_LABEL,
  TICKET_COST_LABEL,
  TICKET_COST_TITLE,
  TICKET_COST_UNKNOWN,
  TICKET_MARKET_UNAVAILABLE,
  TICKET_PRICE_LABEL,
  TICKET_STOP_LABEL,
  TICKET_TRAIL_LABEL,
} from '../constantGroups/trader_chrome';
import { formatMoney } from '../utils/formatMoney';
import type { TopOfBookLike } from './applyTicketDefaults';
import { ManualOrderPriceQuick } from './ManualOrderPriceQuick';
import { ManualOrderQuantityRow } from './ManualOrderQuantityRow';
import { ManualOrderStopControl } from './ManualOrderStopControl';
import {
  usesLimitPrice,
  type ManualOrderType,
  type QuantityMode,
} from './orderEntry';
import type { TicketCostEstimate } from './ticketCost';
import type { QuickPriceKind } from './ticketPriceQuick';
import type { TicketSide } from './ticketSide';

interface Props {
  /** Symbol the Bid / Mid / Ask quick-set reads the book for. */
  symbol?: string;
  /** Live top of book for the quick-set; absent means the buttons grey out. */
  topOfBook?: TopOfBookLike | null;
  /** The book side the limit follows (lit); null when the operator typed a price. */
  priceFollowing?: QuickPriceKind | null;
  /** Bid / Mid / Ask: follow that side (`kind` null stops). Without it a click only sets the price. */
  onPriceFollow?: (kind: QuickPriceKind | null, price: string | null) => void;
  ticketSide: TicketSide;
  allowShort: boolean;
  orderType: ManualOrderType;
  quantityMode: QuantityMode;
  quantityValue: string;
  limitPrice: string;
  stopPrice: string;
  outsideRth: boolean;
  disabled: boolean;
  /** Why `disabled` is set (no Gateway, an order in flight): every locked field says it (ux/whyTip.ts). */
  why?: string | null;
  /** When true, quantity input / units / presets are inert (forced share qty). */
  quantityLocked?: boolean;
  shortDisabledReason?: string | null;
  /** Set while the backend would refuse a MKT (MKT_OUTSIDE_RTH): Market greys out with this title. */
  marketDisabledReason?: string | null;
  /** `Cost · BP after` estimate; omitted (undefined) hides the line. */
  cost?: TicketCostEstimate | null;
  onTicketSideChange: (side: TicketSide) => void;
  onOrderTypeChange: (orderType: ManualOrderType) => void;
  onQuantityModeChange: (mode: QuantityMode) => void;
  onQuantityValueChange: (value: string) => void;
  onLimitPriceChange: (value: string) => void;
  onStopPriceChange: (value: string) => void;
  onOutsideRthChange: (outsideRth: boolean) => void;
}

type PrimaryType = { value: ManualOrderType; label: string; title: string; testId: string };
const PRIMARY_TYPES: readonly PrimaryType[] = [
  { value: 'LMT', label: 'Limit', title: 'Limit order', testId: 'manual-order-type-lmt' },
  {
    value: 'MKT',
    label: 'Market',
    title: TICKER_TRADE_DEFAULT_ORDER_TYPE === 'MKT' ? 'Market (default)' : 'Market order',
    testId: 'manual-order-type-mkt',
  },
];

function money(value: number | null | undefined, decimals: number): string {
  return value == null ? TICKET_COST_UNKNOWN : formatMoney(value, decimals);
}

export function ManualOrderFields({
  symbol = '',
  topOfBook = null,
  priceFollowing = null,
  onPriceFollow,
  ticketSide,
  allowShort,
  orderType,
  quantityMode,
  quantityValue,
  limitPrice,
  stopPrice,
  outsideRth,
  disabled,
  why = null,
  quantityLocked = false,
  shortDisabledReason = null,
  marketDisabledReason = null,
  cost,
  onTicketSideChange,
  onOrderTypeChange,
  onQuantityModeChange,
  onQuantityValueChange,
  onLimitPriceChange,
  onStopPriceChange,
  onOutsideRthChange,
}: Props) {
  const shortBlocked = Boolean(shortDisabledReason);
  // A locked field says why (ux/whyTip.ts): its own block first -- it outlives a
  // reconnect -- then the ticket-wide lock.
  const ticketWhy = disabled ? why || undefined : undefined;
  const shortWhy = shortDisabledReason || ticketWhy;

  return (
    <>
      <div
        className={`manual-order-segment manual-order-side${allowShort ? ' manual-order-side--with-short' : ''}`}
        role="group"
        aria-label={TICKER_TRADE_LABEL_SIDE}
      >
        <button
          type="button"
          className={ticketSide === 'buy' ? 'is-buy' : ''}
          aria-pressed={ticketSide === 'buy'}
          onClick={() => onTicketSideChange('buy')}
          disabled={disabled}
          data-why={ticketWhy}
          data-testid="manual-order-side-buy"
        >
          {TICKER_TRADE_LABEL_BUY}
        </button>
        <button
          type="button"
          className={ticketSide === 'sell' ? 'is-sell' : ''}
          aria-pressed={ticketSide === 'sell'}
          onClick={() => onTicketSideChange('sell')}
          disabled={disabled}
          data-why={ticketWhy}
          data-testid="manual-order-side-sell"
        >
          {TICKER_TRADE_LABEL_SELL}
        </button>
        {allowShort && (
          <button
            type="button"
            className={ticketSide === 'short' ? 'is-short' : ''}
            aria-pressed={ticketSide === 'short'}
            onClick={() => {
              if (!shortBlocked) onTicketSideChange('short');
            }}
            disabled={disabled || shortBlocked}
            data-why={shortWhy}
            data-testid="manual-order-side-short"
          >
            {TICKER_TRADE_LABEL_SHORT}
          </button>
        )}
      </div>
      {allowShort && shortBlocked && (
        <p className="manual-order-hint mot-reason" data-testid="manual-order-short-reason">
          {shortDisabledReason}
        </p>
      )}

      <div
        className="manual-order-segment manual-order-types"
        role="group"
        aria-label={TICKER_TRADE_LABEL_ORDER_TYPE}
      >
        {PRIMARY_TYPES.map((item) => {
          const isActive = orderType === item.value;
          const blocked = item.value === 'MKT' && Boolean(marketDisabledReason);
          const typeWhy = (blocked && marketDisabledReason) || ticketWhy;
          return (
            <button
              key={item.value}
              type="button"
              className={isActive ? 'is-active' : ''}
              aria-pressed={isActive}
              title={typeWhy ? undefined : item.title}
              onClick={() => {
                if (!blocked) onOrderTypeChange(item.value);
              }}
              disabled={disabled || blocked}
              data-why={typeWhy}
              data-testid={item.testId}
            >
              {item.label}
            </button>
          );
        })}
        <ManualOrderStopControl
          orderType={orderType}
          disabled={disabled}
          why={ticketWhy}
          onOrderTypeChange={onOrderTypeChange}
        />
      </div>
      {marketDisabledReason && (
        <p className="mot-reason" data-testid="manual-order-market-reason">
          <b>{TICKET_MARKET_UNAVAILABLE}</b>
          {' -- '}
          <span className="manual-order-lock-note" data-testid="market-outside-rth-note">
            {marketDisabledReason}
          </span>
        </p>
      )}

      {usesLimitPrice(orderType) && (
        <div className="mot-field mot-field--price">
          <label className="mot-field__k" htmlFor="manual-order-limit">
            {TICKET_PRICE_LABEL}
          </label>
          <input
            id="manual-order-limit"
            className="manual-order-price"
            type="number"
            min="0"
            step="0.01"
            value={limitPrice}
            onChange={(event) => onLimitPriceChange(event.target.value)}
            disabled={disabled}
            data-why={ticketWhy}
          />
          <ManualOrderPriceQuick
            symbol={symbol}
            book={topOfBook}
            following={priceFollowing}
            disabled={disabled}
            why={ticketWhy}
            onFollow={
              onPriceFollow ??
              ((_kind, price) => {
                if (price != null) onLimitPriceChange(price);
              })
            }
          />
        </div>
      )}

      {(orderType === 'STP' || orderType === 'STP LMT') && (
        <div className="mot-field mot-field--price">
          <label className="mot-field__k" htmlFor="manual-order-stop">
            {TICKET_STOP_LABEL}
          </label>
          <input
            id="manual-order-stop"
            className="manual-order-price"
            type="number"
            min="0"
            step="0.01"
            value={stopPrice}
            onChange={(event) => onStopPriceChange(event.target.value)}
            disabled={disabled}
            data-why={ticketWhy}
          />
        </div>
      )}

      {orderType === 'TRAIL' && (
        <div className="mot-field mot-field--price">
          <label className="mot-field__k" htmlFor="manual-order-trail">
            {TICKET_TRAIL_LABEL}
          </label>
          <input
            id="manual-order-trail"
            className="manual-order-price"
            type="number"
            min="0"
            step="0.01"
            value={stopPrice}
            onChange={(event) => onStopPriceChange(event.target.value)}
            disabled={disabled}
            data-why={ticketWhy}
            data-testid="manual-order-trail"
          />
        </div>
      )}

      <div className="mot-field mot-field--qty">
        <ManualOrderQuantityRow
          quantityMode={quantityMode}
          quantityValue={quantityValue}
          disabled={disabled}
          why={ticketWhy}
          quantityLocked={quantityLocked}
          onQuantityModeChange={onQuantityModeChange}
          onQuantityValueChange={onQuantityValueChange}
        />
      </div>

      <div className="mot-row mot-row--foot">
        <label className="manual-order-extended" htmlFor="manual-order-extended">
          <input
            id="manual-order-extended"
            className="manual-order-extended-check"
            type="checkbox"
            checked={outsideRth}
            onChange={(event) => onOutsideRthChange(event.target.checked)}
            disabled={disabled}
            data-why={ticketWhy}
            data-testid="manual-order-extended"
          />
          {TICKER_TRADE_LABEL_TRADING_HOURS}
        </label>
        {cost !== undefined && (
          <span className="mot-cost" data-testid="manual-order-cost" title={cost?.note || TICKET_COST_TITLE}>
            {TICKET_COST_LABEL} <b>{money(cost?.cost, 2)}</b>
            {' · '}
            {TICKET_BP_AFTER_LABEL} <b>{money(cost?.buyingPowerAfter, 0)}</b>
          </span>
        )}
      </div>
    </>
  );
}
