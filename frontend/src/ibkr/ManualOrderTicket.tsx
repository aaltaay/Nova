import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  TICKER_TRADE_DEFAULT_ORDER_TYPE,
  TICKER_TRADE_DEFAULT_QTY,
  TICKER_TRADE_FORCE_QTY,
  TICKER_TRADE_PLACE_ORDER_LABEL,
  TICKER_TRADE_PLACE_PAPER_ORDER_LABEL,
  TICKER_TRADE_UNLOCK_LABEL,
} from '../constants';
import {
  buildManualOrder,
  forcedManualOrderQty,
  presetsForQuantityMode,
  type ManualOrderSide,
  type ManualOrderType,
  type QuantityMode,
} from './orderEntry';
import { ManualOrderFields } from './ManualOrderFields';
import { PlaceOrderConfirmDialog } from './PlaceOrderConfirmDialog';
import { TradingPinDialog } from './TradingPinDialog';
import { placeIbkrOrder, type PlaceOrderResult } from './placeOrder';
import {
  readSkipPlaceConfirm,
  writeSkipPlaceConfirm,
} from './placeConfirmPrefs';
import {
  readTicketSessionUnlocked,
  tryUnlockTicketSession,
} from './ticketUnlock';
import type { IbkrAccountSummary, IbkrMode, IbkrPosition } from './types';

interface Props {
  symbol: string;
  mode: IbkrMode;
  connected: boolean;
  spendStatus?: string;
  summary: IbkrAccountSummary | null;
  position: IbkrPosition | null;
  referencePrice: number | null;
  onOrderPlaced?: (result: PlaceOrderResult) => void;
}

const FORCED_QTY = forcedManualOrderQty();
const QTY_LOCKED = FORCED_QTY != null;

export function ManualOrderTicket({
  symbol,
  mode,
  connected,
  spendStatus,
  summary,
  position,
  referencePrice,
  onOrderPlaced,
}: Props) {
  const [side, setSide] = useState<ManualOrderSide>('BUY');
  const [orderType, setOrderType] = useState<ManualOrderType>(
    TICKER_TRADE_DEFAULT_ORDER_TYPE,
  );
  const [quantityMode, setQuantityMode] = useState<QuantityMode>('shares');
  const [quantityValue, setQuantityValue] = useState(
    String(FORCED_QTY ?? TICKER_TRADE_DEFAULT_QTY),
  );
  const [limitPrice, setLimitPrice] = useState('');
  const [stopPrice, setStopPrice] = useState('');
  const [outsideRth, setOutsideRth] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [sessionUnlocked, setSessionUnlocked] = useState(readTicketSessionUnlocked);
  const [confirmSummary, setConfirmSummary] = useState<string | null>(null);
  const [pinDialogOpen, setPinDialogOpen] = useState(false);

  const displayQuantityMode: QuantityMode = QTY_LOCKED ? 'shares' : quantityMode;
  const displayQuantityValue = QTY_LOCKED
    ? String(FORCED_QTY)
    : quantityValue;

  useEffect(() => {
    setSide('BUY');
    setOrderType(TICKER_TRADE_DEFAULT_ORDER_TYPE);
    setQuantityMode('shares');
    setQuantityValue(String(FORCED_QTY ?? TICKER_TRADE_DEFAULT_QTY));
    setLimitPrice(referencePrice != null ? referencePrice.toFixed(2) : '');
    setStopPrice('');
    setOutsideRth(false);
    setResult(null);
    setConfirmSummary(null);
  }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (referencePrice != null && !limitPrice) {
      setLimitPrice(referencePrice.toFixed(2));
    }
  }, [referencePrice, limitPrice]);

  const spendLocked =
    spendStatus === 'locked' || spendStatus === 'locked_live_unconfirmed';
  const needsPinUnlock = !sessionUnlocked;

  function selectOrderType(next: ManualOrderType) {
    setOrderType(next);
    if (next !== 'LMT') setOutsideRth(false);
    setResult(null);
  }

  function selectQuantityMode(next: QuantityMode) {
    if (QTY_LOCKED) return;
    setQuantityMode(next);
    setQuantityValue(String(presetsForQuantityMode(next)[0]));
    setResult(null);
  }

  function onQuantityValueChange(next: string) {
    if (QTY_LOCKED) return;
    setQuantityValue(next);
  }

  function submitPin(pin: string): boolean {
    const ok = tryUnlockTicketSession(pin);
    if (ok) {
      setSessionUnlocked(true);
      setResult(null);
      setPinDialogOpen(false);
    }
    return ok;
  }

  async function executeOrder() {
    if (!connected || submitting) return;
    if (spendLocked) {
      setResult({
        ok: false,
        text: 'Orders remain locked by Nova environment safety settings.',
      });
      return;
    }

    const built = buildManualOrder(
      {
        symbol,
        side,
        orderType,
        quantityMode: displayQuantityMode,
        quantityValue: displayQuantityValue,
        limitPrice,
        stopPrice,
        outsideRth,
      },
      {
        marketReferencePrice: referencePrice,
        buyingPower: summary?.BuyingPower ?? null,
        positionQty: position?.qty ?? null,
      },
    );
    if (!built.ok) {
      setResult({ ok: false, text: built.error });
      return;
    }

    setSubmitting(true);
    setResult(null);
    try {
      const response = await placeIbkrOrder(built.payload);
      setResult({
        ok: response.ok,
        text: response.ok
          ? `Order #${response.order_id} placed (${response.mode ?? mode})`
          : response.error ?? 'Order failed',
      });
      if (response.ok) onOrderPlaced?.(response);
    } catch {
      setResult({ ok: false, text: 'Network error' });
    } finally {
      setSubmitting(false);
    }
  }

  function requestPlaceOrder() {
    if (!connected || submitting) return;
    if (spendLocked) {
      setResult({
        ok: false,
        text: 'Orders remain locked by Nova environment safety settings.',
      });
      return;
    }

    const built = buildManualOrder(
      {
        symbol,
        side,
        orderType,
        quantityMode: displayQuantityMode,
        quantityValue: displayQuantityValue,
        limitPrice,
        stopPrice,
        outsideRth,
      },
      {
        marketReferencePrice: referencePrice,
        buyingPower: summary?.BuyingPower ?? null,
        positionQty: position?.qty ?? null,
      },
    );
    if (!built.ok) {
      setResult({ ok: false, text: built.error });
      return;
    }

    const priceText =
      orderType === 'LMT'
        ? ` @ $${limitPrice}`
        : orderType === 'STP'
          ? ` stop $${stopPrice}`
          : '';
    const hoursText = outsideRth ? ' including extended hours' : ' during regular hours';
    const summaryText =
      `${side} ${built.quantity} ${symbol.toUpperCase()} (${orderType}${priceText})` +
      `${hoursText} on the ${mode.toUpperCase()} account.`;

    if (readSkipPlaceConfirm()) {
      void executeOrder();
      return;
    }
    setConfirmSummary(summaryText);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!connected || submitting) return;

    if (needsPinUnlock) {
      setPinDialogOpen(true);
      return;
    }

    requestPlaceOrder();
  }

  const isPaper = mode === 'paper';
  const placeLabel = isPaper
    ? TICKER_TRADE_PLACE_PAPER_ORDER_LABEL
    : TICKER_TRADE_PLACE_ORDER_LABEL;

  const buttonText = !connected
    ? 'Connect IB Gateway'
    : needsPinUnlock
      ? TICKER_TRADE_UNLOCK_LABEL
      : submitting
        ? 'Placing…'
        : placeLabel;

  const buttonDisabled = !connected || submitting;

  const buttonTitle = !connected
    ? 'Connect IB Gateway first'
    : needsPinUnlock
      ? `Enter unlock code, then ${placeLabel}`
      : spendLocked
        ? 'IBKR orders remain gated by environment safety settings'
        : QTY_LOCKED
          ? `Quantity locked to ${TICKER_TRADE_FORCE_QTY} share (temporary safety)`
          : isPaper
            ? 'Review and place this order on the IBKR paper account'
            : 'Review and place this order';

  return (
    <form className="manual-order-ticket" onSubmit={submit}>
      <ManualOrderFields
        side={side}
        orderType={orderType}
        quantityMode={displayQuantityMode}
        quantityValue={displayQuantityValue}
        limitPrice={limitPrice}
        stopPrice={stopPrice}
        outsideRth={outsideRth}
        disabled={!connected || submitting}
        quantityLocked={QTY_LOCKED}
        onSideChange={setSide}
        onOrderTypeChange={selectOrderType}
        onQuantityModeChange={selectQuantityMode}
        onQuantityValueChange={onQuantityValueChange}
        onLimitPriceChange={setLimitPrice}
        onStopPriceChange={setStopPrice}
        onOutsideRthChange={setOutsideRth}
      />

      <Button
        type="submit"
        variant="default"
        size="lg"
        className={
          isPaper && !needsPinUnlock && connected
            ? 'manual-order-submit manual-order-submit--paper mt-1 w-full'
            : 'manual-order-submit mt-1 w-full'
        }
        disabled={buttonDisabled}
        title={buttonTitle}
      >
        {buttonText}
      </Button>

      {needsPinUnlock && connected && (
        <span className="manual-order-lock-note">
          Enter the unlock code to enable {placeLabel}.
        </span>
      )}
      {sessionUnlocked && spendLocked && (
        <span className="manual-order-lock-note">
          Session unlocked. IBKR env gates may still reject the order until orders are enabled.
        </span>
      )}
      {QTY_LOCKED && sessionUnlocked && (
        <span className="manual-order-lock-note">
          Quantity locked to {FORCED_QTY} share for safety — presets ignored.
        </span>
      )}
      {result && (
        <span className={`manual-order-result ${result.ok ? 'ok' : 'err'}`}>
          {result.text}
        </span>
      )}

      <PlaceOrderConfirmDialog
        open={confirmSummary != null}
        summary={confirmSummary ?? ''}
        onCancel={() => setConfirmSummary(null)}
        onConfirm={skipNextTime => {
          if (skipNextTime) writeSkipPlaceConfirm(true);
          setConfirmSummary(null);
          void executeOrder();
        }}
      />

      <TradingPinDialog
        open={pinDialogOpen}
        onSubmit={submitPin}
        onCancel={() => setPinDialogOpen(false)}
      />
    </form>
  );
}
