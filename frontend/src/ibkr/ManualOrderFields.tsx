import {
  TICKER_TRADE_DEFAULT_ORDER_TYPE,
  TICKER_TRADE_LABEL_LIMIT_PRICE,
  TICKER_TRADE_LABEL_ORDER_TYPE,
  TICKER_TRADE_LABEL_SIDE,
  TICKER_TRADE_LABEL_STOP_PRICE,
  TICKER_TRADE_LABEL_TRAIL_AMOUNT,
  TICKER_TRADE_LABEL_TRADING_HOURS,
} from '../constants';
import {
  TICKER_TRADE_LABEL_BUY,
  TICKER_TRADE_LABEL_SELL,
  TICKER_TRADE_LABEL_SHORT,
} from '../constantGroups/shortability';
import { ManualOrderQuantityRow } from './ManualOrderQuantityRow';
import { ManualOrderStopControl } from './ManualOrderStopControl';
import {
  usesLimitPrice,
  type ManualOrderType,
  type QuantityMode,
} from './orderEntry';
import type { TicketSide } from './ticketSide';

interface Props {
  ticketSide: TicketSide;
  allowShort: boolean;
  orderType: ManualOrderType;
  quantityMode: QuantityMode;
  quantityValue: string;
  limitPrice: string;
  stopPrice: string;
  outsideRth: boolean;
  disabled: boolean;
  /** When true, quantity input / units / presets are inert (forced share qty). */
  quantityLocked?: boolean;
  shortDisabledReason?: string | null;
  onTicketSideChange: (side: TicketSide) => void;
  onOrderTypeChange: (orderType: ManualOrderType) => void;
  onQuantityModeChange: (mode: QuantityMode) => void;
  onQuantityValueChange: (value: string) => void;
  onLimitPriceChange: (value: string) => void;
  onStopPriceChange: (value: string) => void;
  onOutsideRthChange: (outsideRth: boolean) => void;
}

const PRIMARY_TYPES: readonly { value: ManualOrderType; label: string; title?: string }[] = [
  { value: 'LMT', label: 'Limit', title: 'Limit order' },
  {
    value: 'MKT',
    label: 'Market',
    title:
      TICKER_TRADE_DEFAULT_ORDER_TYPE === 'MKT'
        ? 'Market (default)'
        : 'Market order',
  },
];

export function ManualOrderFields({
  ticketSide,
  allowShort,
  orderType,
  quantityMode,
  quantityValue,
  limitPrice,
  stopPrice,
  outsideRth,
  disabled,
  quantityLocked = false,
  shortDisabledReason = null,
  onTicketSideChange,
  onOrderTypeChange,
  onQuantityModeChange,
  onQuantityValueChange,
  onLimitPriceChange,
  onStopPriceChange,
  onOutsideRthChange,
}: Props) {
  const shortBlocked = Boolean(shortDisabledReason);

  return (
    <>
      <label className="manual-order-label">{TICKER_TRADE_LABEL_SIDE}</label>
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
          data-testid="manual-order-side-sell"
        >
          {TICKER_TRADE_LABEL_SELL}
        </button>
        {allowShort && (
          <button
            type="button"
            className={ticketSide === 'short' ? 'is-short' : ''}
            aria-pressed={ticketSide === 'short'}
            title={shortBlocked ? shortDisabledReason ?? undefined : undefined}
            onClick={() => {
              if (!shortBlocked) onTicketSideChange('short');
            }}
            disabled={disabled || shortBlocked}
            data-testid="manual-order-side-short"
          >
            {TICKER_TRADE_LABEL_SHORT}
          </button>
        )}
      </div>
      {allowShort && shortBlocked && (
        <p className="manual-order-hint" data-testid="manual-order-short-reason">
          {shortDisabledReason}
        </p>
      )}

      <label className="manual-order-label">{TICKER_TRADE_LABEL_ORDER_TYPE}</label>
      <div
        className="manual-order-segment manual-order-types"
        role="group"
        aria-label={TICKER_TRADE_LABEL_ORDER_TYPE}
      >
        {PRIMARY_TYPES.map(item => {
          const isDefault = item.value === TICKER_TRADE_DEFAULT_ORDER_TYPE;
          const isActive = orderType === item.value;
          return (
            <button
              key={item.value}
              type="button"
              className={`${isActive ? 'is-active' : ''}${isDefault ? ' is-default' : ''}`}
              aria-pressed={isActive}
              title={item.title}
              onClick={() => onOrderTypeChange(item.value)}
              disabled={disabled}
            >
              {item.label}
              {isDefault ? (
                <span className="manual-order-default-tag" aria-hidden>
                  Default
                </span>
              ) : null}
            </button>
          );
        })}
        <ManualOrderStopControl
          orderType={orderType}
          disabled={disabled}
          onOrderTypeChange={onOrderTypeChange}
        />
      </div>

      <ManualOrderQuantityRow
        quantityMode={quantityMode}
        quantityValue={quantityValue}
        disabled={disabled}
        quantityLocked={quantityLocked}
        onQuantityModeChange={onQuantityModeChange}
        onQuantityValueChange={onQuantityValueChange}
      />

      {usesLimitPrice(orderType) && (
        <>
          <label className="manual-order-label" htmlFor="manual-order-limit">
            {TICKER_TRADE_LABEL_LIMIT_PRICE}
          </label>
          <input
            id="manual-order-limit"
            className="manual-order-price"
            type="number"
            min="0"
            step="0.01"
            value={limitPrice}
            onChange={event => onLimitPriceChange(event.target.value)}
            disabled={disabled}
          />
        </>
      )}

      {(orderType === 'STP' || orderType === 'STP LMT') && (
        <>
          <label className="manual-order-label" htmlFor="manual-order-stop">
            {TICKER_TRADE_LABEL_STOP_PRICE}
          </label>
          <input
            id="manual-order-stop"
            className="manual-order-price"
            type="number"
            min="0"
            step="0.01"
            value={stopPrice}
            onChange={event => onStopPriceChange(event.target.value)}
            disabled={disabled}
          />
        </>
      )}

      {orderType === 'TRAIL' && (
        <>
          <label className="manual-order-label" htmlFor="manual-order-trail">
            {TICKER_TRADE_LABEL_TRAIL_AMOUNT}
          </label>
          <input
            id="manual-order-trail"
            className="manual-order-price"
            type="number"
            min="0"
            step="0.01"
            value={stopPrice}
            onChange={event => onStopPriceChange(event.target.value)}
            disabled={disabled}
            data-testid="manual-order-trail"
          />
        </>
      )}

      <label className="manual-order-extended" htmlFor="manual-order-extended">
        <input
          id="manual-order-extended"
          className="manual-order-extended-check"
          type="checkbox"
          checked={outsideRth}
          onChange={event => onOutsideRthChange(event.target.checked)}
          disabled={disabled}
          data-testid="manual-order-extended"
        />
        {TICKER_TRADE_LABEL_TRADING_HOURS}
      </label>
    </>
  );
}
