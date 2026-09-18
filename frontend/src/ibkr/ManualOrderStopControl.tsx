import { useEffect, useRef, useState } from 'react';
import {
  TICKER_TRADE_LABEL_STOP,
  TICKER_TRADE_LABEL_STOP_LIMIT,
  TICKER_TRADE_LABEL_STOP_TYPES,
  TICKER_TRADE_LABEL_TRAILING_STOP,
} from '../constants';
import { isStopFamilyType, type ManualOrderType } from './orderEntry';

interface Props {
  orderType: ManualOrderType;
  disabled: boolean;
  onOrderTypeChange: (orderType: ManualOrderType) => void;
}

export function ManualOrderStopControl({
  orderType,
  disabled,
  onOrderTypeChange,
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const familyActive = isStopFamilyType(orderType);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (rootRef.current?.contains(event.target as Node)) return;
      setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  function pick(next: ManualOrderType) {
    onOrderTypeChange(next);
    setOpen(false);
  }

  return (
    <div className="manual-order-stop-wrap" ref={rootRef}>
      <div className={`manual-order-stop-split${familyActive ? ' is-active' : ''}`}>
        <button
          type="button"
          className={familyActive ? 'is-active' : ''}
          aria-pressed={orderType === 'STP'}
          title="Stop order"
          onClick={() => pick('STP')}
          disabled={disabled}
          data-testid="manual-order-type-stop"
        >
          {TICKER_TRADE_LABEL_STOP}
        </button>
        <button
          type="button"
          className={`manual-order-stop-caret${open ? ' is-open' : ''}`}
          aria-label={TICKER_TRADE_LABEL_STOP_TYPES}
          aria-expanded={open}
          aria-haspopup="menu"
          title={TICKER_TRADE_LABEL_STOP_TYPES}
          onClick={event => {
            event.stopPropagation();
            setOpen(current => !current);
          }}
          disabled={disabled}
          data-testid="manual-order-stop-caret"
        >
          ^
        </button>
      </div>
      {open ? (
        <div
          className="manual-order-stop-flyout"
          role="menu"
          data-testid="manual-order-stop-flyout"
        >
          <button
            type="button"
            role="menuitem"
            className={orderType === 'STP LMT' ? 'is-active' : ''}
            onClick={() => pick('STP LMT')}
            disabled={disabled}
            data-testid="manual-order-type-stop-limit"
          >
            {TICKER_TRADE_LABEL_STOP_LIMIT}
          </button>
          <button
            type="button"
            role="menuitem"
            className={orderType === 'TRAIL' ? 'is-active' : ''}
            onClick={() => pick('TRAIL')}
            disabled={disabled}
            data-testid="manual-order-type-trail"
          >
            {TICKER_TRADE_LABEL_TRAILING_STOP}
          </button>
        </div>
      ) : null}
    </div>
  );
}
