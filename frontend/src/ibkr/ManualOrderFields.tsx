import {
  TICKER_TRADE_DEFAULT_ORDER_TYPE,
  TICKER_TRADE_LABEL_LIMIT_PRICE,
  TICKER_TRADE_LABEL_ORDER_TYPE,
  TICKER_TRADE_LABEL_SIDE,
  TICKER_TRADE_LABEL_STOP_PRICE,
  TICKER_TRADE_LABEL_TRADING_HOURS,
} from '../constants';
import {
  TICKER_TRADE_LABEL_DIRECTION,
  TICKER_TRADE_LABEL_LONG,
  TICKER_TRADE_LABEL_SHORT,
} from '../constantGroups/shortability';
import { ManualOrderQuantityRow } from './ManualOrderQuantityRow';
import {
  type ManualOrderSide,
  type ManualOrderType,
  type QuantityMode,
} from './orderEntry';

interface Props {
  side: ManualOrderSide;
  orderType: ManualOrderType;
  quantityMode: QuantityMode;
  quantityValue: string;
  limitPrice: string;
  stopPrice: string;
  outsideRth: boolean;
  disabled: boolean;
  /** When true, quantity input / units / presets are inert (forced share qty). */
  quantityLocked?: boolean;
  /** Phase K: Long vs Short opening direction. */
  shortEntry?: boolean;
  shortDisabledReason?: string | null;
  onDirectionChange?: (shortEntry: boolean) => void;
  onSideChange: (side: ManualOrderSide) => void;
  onOrderTypeChange: (orderType: ManualOrderType) => void;
  onQuantityModeChange: (mode: QuantityMode) => void;
  onQuantityValueChange: (value: string) => void;
  onLimitPriceChange: (value: string) => void;
  onStopPriceChange: (value: string) => void;
  onOutsideRthChange: (outsideRth: boolean) => void;
}

const ORDER_TYPES: readonly { value: ManualOrderType; label: string; title?: string }[] = [
  { value: 'LMT', label: 'Limit', title: 'Limit order' },
  {
    value: 'MKT',
    label: 'Market',
    title:
      TICKER_TRADE_DEFAULT_ORDER_TYPE === 'MKT'
        ? 'Market (default)'
        : 'Market order',
  },
  { value: 'STP', label: 'Stop', title: 'Stop order' },
];

export function ManualOrderFields({
  side,
  orderType,
  quantityMode,
  quantityValue,
  limitPrice,
  stopPrice,
  outsideRth,
  disabled,
  quantityLocked = false,
  shortEntry = false,
  shortDisabledReason = null,
  onDirectionChange,
  onSideChange,
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
      {onDirectionChange && (
        <>
          <label className="manual-order-label">{TICKER_TRADE_LABEL_DIRECTION}</label>
          <div
            className="manual-order-segment manual-order-direction"
            role="group"
            aria-label={TICKER_TRADE_LABEL_DIRECTION}
          >
            <button
              type="button"
              className={!shortEntry ? 'is-buy' : ''}
              aria-pressed={!shortEntry}
              onClick={() => onDirectionChange(false)}
              disabled={disabled}
            >
              {TICKER_TRADE_LABEL_LONG}
            </button>
            <button
              type="button"
              className={shortEntry ? 'is-sell' : ''}
              aria-pressed={shortEntry}
              title={shortBlocked ? shortDisabledReason ?? undefined : undefined}
              onClick={() => {
                if (!shortBlocked) onDirectionChange(true);
              }}
              disabled={disabled || shortBlocked}
              data-testid="manual-order-short-direction"
            >
              {TICKER_TRADE_LABEL_SHORT}
            </button>
          </div>
          {shortBlocked && (
            <p className="manual-order-hint" data-testid="manual-order-short-reason">
              {shortDisabledReason}
            </p>
          )}
        </>
      )}

      <label className="manual-order-label">{TICKER_TRADE_LABEL_SIDE}</label>
      <div
        className="manual-order-segment manual-order-side"
        role="group"
        aria-label={TICKER_TRADE_LABEL_SIDE}
      >
        <button
          type="button"
          className={side === 'BUY' ? 'is-buy' : ''}
          aria-pressed={side === 'BUY'}
          onClick={() => onSideChange('BUY')}
          disabled={disabled || shortEntry}
        >
          Buy
        </button>
        <button
          type="button"
          className={side === 'SELL' ? 'is-sell' : ''}
          aria-pressed={side === 'SELL'}
          onClick={() => onSideChange('SELL')}
          disabled={disabled}
        >
          Sell
        </button>
      </div>

      <label className="manual-order-label">{TICKER_TRADE_LABEL_ORDER_TYPE}</label>
      <div
        className="manual-order-segment manual-order-types"
        role="group"
        aria-label={TICKER_TRADE_LABEL_ORDER_TYPE}
      >
        {ORDER_TYPES.map(item => {
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
      </div>

      <ManualOrderQuantityRow
        quantityMode={quantityMode}
        quantityValue={quantityValue}
        disabled={disabled}
        quantityLocked={quantityLocked}
        onQuantityModeChange={onQuantityModeChange}
        onQuantityValueChange={onQuantityValueChange}
      />

      {orderType === 'LMT' && (
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

      {orderType === 'STP' && (
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

      <label className="manual-order-label" htmlFor="manual-order-hours">
        {TICKER_TRADE_LABEL_TRADING_HOURS}
      </label>
      <select
        id="manual-order-hours"
        value={outsideRth ? 'extended' : 'regular'}
        onChange={event => onOutsideRthChange(event.target.value === 'extended')}
        disabled={disabled || orderType !== 'LMT'}
        title={orderType === 'LMT' ? undefined : 'Extended hours supports Limit orders only'}
      >
        <option value="regular">Regular Hours</option>
        <option value="extended">Include Extended Hours</option>
      </select>
    </>
  );
}
