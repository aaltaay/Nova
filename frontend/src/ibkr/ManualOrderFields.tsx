import { useMemo } from 'react';
import {
  TICKER_TRADE_DEFAULT_ORDER_TYPE,
  TICKER_TRADE_FORCE_QTY,
  TICKER_TRADE_LABEL_LIMIT_PRICE,
  TICKER_TRADE_LABEL_ORDER_TYPE,
  TICKER_TRADE_LABEL_QUANTITY,
  TICKER_TRADE_LABEL_SIDE,
  TICKER_TRADE_LABEL_STOP_PRICE,
  TICKER_TRADE_LABEL_TRADING_HOURS,
} from '../constants';
import {
  presetsForQuantityMode,
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

const QUANTITY_MODES: readonly { value: QuantityMode; label: string; title: string }[] = [
  { value: 'shares', label: 'Qty', title: 'Quantity in shares' },
  { value: 'percent', label: '%', title: 'Percentage of Buying Power or position' },
  { value: 'dollars', label: '$', title: 'Dollar amount converted to shares' },
];

function formatPreset(value: number, mode: QuantityMode): string {
  if (mode === 'percent') return `${value}%`;
  if (mode === 'dollars') return `$${value.toLocaleString('en-US')}`;
  return String(value);
}

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
  onSideChange,
  onOrderTypeChange,
  onQuantityModeChange,
  onQuantityValueChange,
  onLimitPriceChange,
  onStopPriceChange,
  onOutsideRthChange,
}: Props) {
  const presets = useMemo(
    () => presetsForQuantityMode(quantityMode),
    [quantityMode],
  );
  const qtyDisabled = disabled || quantityLocked;
  const qtyLockTitle =
    quantityLocked && TICKER_TRADE_FORCE_QTY != null
      ? `Quantity locked to ${TICKER_TRADE_FORCE_QTY} share (temporary safety)`
      : undefined;

  return (
    <>
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
          disabled={disabled}
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

      <label className="manual-order-label" htmlFor="manual-order-quantity">
        {TICKER_TRADE_LABEL_QUANTITY}
      </label>
      <div className="manual-order-quantity-row">
        <input
          id="manual-order-quantity"
          type="number"
          min="0"
          step={quantityMode === 'shares' ? '1' : '0.01'}
          value={quantityValue}
          onChange={event => onQuantityValueChange(event.target.value)}
          disabled={qtyDisabled}
          readOnly={quantityLocked}
          title={qtyLockTitle}
        />
        <div className="manual-order-unit-toggle" role="group" aria-label="Quantity unit">
          {QUANTITY_MODES.map(item => (
            <button
              key={item.value}
              type="button"
              className={quantityMode === item.value ? 'is-active' : ''}
              aria-pressed={quantityMode === item.value}
              title={qtyLockTitle ?? item.title}
              onClick={() => onQuantityModeChange(item.value)}
              disabled={qtyDisabled}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div className="manual-order-presets" aria-label="Quick quantity presets">
        {presets.map(value => (
          <button
            key={value}
            type="button"
            onClick={() => onQuantityValueChange(String(value))}
            disabled={qtyDisabled}
            title={qtyLockTitle}
          >
            {formatPreset(value, quantityMode)}
          </button>
        ))}
      </div>

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
