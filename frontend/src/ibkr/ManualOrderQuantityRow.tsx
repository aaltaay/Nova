import { useMemo } from 'react';
import {
  TICKER_TRADE_FORCE_QTY,
  TICKER_TRADE_LABEL_QUANTITY,
  TICKER_TRADE_QTY_NUDGE,
  TICKER_TRADE_QTY_NUDGE_MINUS_LABEL,
  TICKER_TRADE_QTY_NUDGE_PLUS_LABEL,
} from '../constants';
import {
  nudgeQuantityValue,
  presetsForQuantityMode,
  type QuantityMode,
} from './orderEntry';

interface Props {
  quantityMode: QuantityMode;
  quantityValue: string;
  disabled: boolean;
  /** Why `disabled` is set -- each locked control says it (ux/whyTip.ts). */
  why?: string | null;
  quantityLocked?: boolean;
  onQuantityModeChange: (mode: QuantityMode) => void;
  onQuantityValueChange: (value: string) => void;
}

const QUANTITY_MODES: readonly {
  value: QuantityMode;
  label: string;
  title: string;
}[] = [
  { value: 'shares', label: 'Qty', title: 'Quantity in shares' },
  { value: 'percent', label: '%', title: 'Percentage of Buying Power or position' },
  { value: 'dollars', label: '$', title: 'Dollar amount converted to shares' },
];

/** Chip text only -- the mode toggle already shows Qty / % / $. */
function formatPreset(value: number): string {
  return String(value);
}

function presetAria(value: number, mode: QuantityMode): string {
  if (mode === 'percent') return `${value} percent`;
  if (mode === 'dollars') return `${value} dollars`;
  return `${value} shares`;
}

function SharesModeIcon() {
  return (
    <svg
      className="manual-order-qty-icon"
      viewBox="0 0 16 16"
      width="11"
      height="11"
      aria-hidden
    >
      <ellipse cx="8" cy="3.3" rx="5.1" ry="1.7" fill="currentColor" />
      <path
        d="M2.9 3.3v3c0 .95 2.25 1.7 5.1 1.7s5.1-.75 5.1-1.7v-3"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.15"
      />
      <path
        d="M2.9 6.3v3c0 .95 2.25 1.7 5.1 1.7s5.1-.75 5.1-1.7v-3"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.15"
      />
      <path
        d="M2.9 9.3v2.5c0 .95 2.25 1.7 5.1 1.7s5.1-.75 5.1-1.7V9.3"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.15"
      />
    </svg>
  );
}

export function ManualOrderQuantityRow({
  quantityMode,
  quantityValue,
  disabled,
  why = null,
  quantityLocked = false,
  onQuantityModeChange,
  onQuantityValueChange,
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
  // A locked control says why (ux/whyTip.ts): the size lock outlives a
  // reconnect, so it answers before the ticket's own lock.
  const qtyWhy = qtyLockTitle ?? (disabled ? why || undefined : undefined);

  function nudge(direction: 1 | -1) {
    onQuantityValueChange(
      nudgeQuantityValue(
        quantityValue,
        direction * TICKER_TRADE_QTY_NUDGE,
        quantityMode,
      ),
    );
  }

  return (
    <>
      <label className="manual-order-label" htmlFor="manual-order-quantity">
        {TICKER_TRADE_LABEL_QUANTITY}
      </label>
      <div
        className="manual-order-quantity-row"
        data-testid="manual-order-quantity-row"
      >
        <input
          id="manual-order-quantity"
          className="manual-order-quantity-input"
          type="number"
          min="0"
          step={quantityMode === 'shares' ? '1' : '0.01'}
          value={quantityValue}
          onChange={event => onQuantityValueChange(event.target.value)}
          disabled={qtyDisabled}
          readOnly={quantityLocked}
          data-why={qtyWhy}
        />
        <div className="manual-order-unit-toggle" role="group" aria-label="Quantity unit">
          {QUANTITY_MODES.map(item => (
            <button
              key={item.value}
              type="button"
              className={quantityMode === item.value ? 'is-active' : ''}
              aria-pressed={quantityMode === item.value}
              aria-label={item.title}
              title={qtyWhy ? undefined : item.title}
              data-testid={`manual-order-qty-mode-${item.value}`}
              onClick={() => onQuantityModeChange(item.value)}
              disabled={qtyDisabled}
              data-why={qtyWhy}
            >
              {item.value === 'shares' ? <SharesModeIcon /> : item.label}
            </button>
          ))}
        </div>
        <span className="manual-order-quantity-rule" aria-hidden />
        <div className="manual-order-presets" aria-label="Quick quantity presets">
          {presets.map(value => (
            <button
              key={value}
              type="button"
              onClick={() => onQuantityValueChange(String(value))}
              disabled={qtyDisabled}
              data-why={qtyWhy}
              aria-label={presetAria(value, quantityMode)}
              title={qtyWhy ? undefined : presetAria(value, quantityMode)}
            >
              {formatPreset(value)}
            </button>
          ))}
          <button
            type="button"
            data-testid="manual-order-qty-nudge-plus"
            aria-label={`Increase quantity by ${TICKER_TRADE_QTY_NUDGE}`}
            title={qtyWhy ? undefined : `Increase by ${TICKER_TRADE_QTY_NUDGE}`}
            onClick={() => nudge(1)}
            disabled={qtyDisabled}
            data-why={qtyWhy}
          >
            {TICKER_TRADE_QTY_NUDGE_PLUS_LABEL}
          </button>
          <button
            type="button"
            data-testid="manual-order-qty-nudge-minus"
            aria-label={`Decrease quantity by ${TICKER_TRADE_QTY_NUDGE}`}
            title={qtyWhy ? undefined : `Decrease by ${TICKER_TRADE_QTY_NUDGE}`}
            onClick={() => nudge(-1)}
            disabled={qtyDisabled}
            data-why={qtyWhy}
          >
            {TICKER_TRADE_QTY_NUDGE_MINUS_LABEL}
          </button>
        </div>
      </div>
    </>
  );
}
