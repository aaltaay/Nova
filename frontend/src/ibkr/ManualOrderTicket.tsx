import { useEffect, useState } from 'react';
import {
  beginBrowserExecutionTiming,
  captureBrowserAction,
} from '../execution_latency';
import {
  buildManualOrder,
  forcedManualOrderQty,
  presetsForQuantityMode,
  type ManualOrderSide,
  type ManualOrderType,
  type QuantityMode,
} from './orderEntry';
import {
  SHORTABILITY_NOT_SHORTABLE,
  SHORTABILITY_SHORT_DISABLED,
  SHORTABILITY_STALE,
} from '../constantGroups/shortability';
import { useTopOfBook } from '../hotkeys/TopOfBookContext';
import type { IbkrListingFlags } from '../types/ticker';
import { applyTicketDefaults, seedPricesForSide } from './applyTicketDefaults';
import { ManualOrderFields } from './ManualOrderFields';
import { ManualOrderFooter } from './ManualOrderFooter';
import { executionTransportError } from './executionTransportError';
import { notifyOrderRejected } from './notifyOrderRejected';
import { placeIbkrOrder, type PlaceOrderResult } from './placeOrder';
import { readSkipPlaceConfirm } from './placeConfirmPrefs';
import { resolveShortabilityState } from './ShortabilityChip';
import {
  readTicketSessionUnlocked,
  subscribeTicketSessionUnlock,
  tryUnlockTicketSession,
} from './ticketUnlock';
import type { IbkrAccountSummary, IbkrMode, IbkrPosition } from './types';
import { useIbkrStatus } from './useIbkrStatus';

interface Props {
  symbol: string;
  mode: IbkrMode;
  connected: boolean;
  spendStatus?: string;
  summary: IbkrAccountSummary | null;
  position: IbkrPosition | null;
  referencePrice: number | null;
  listingIbkr?: IbkrListingFlags | null;
  onOrderPlaced?: (result: PlaceOrderResult) => void;
}

function shortDisabledReason(
  shortEnabled: boolean | undefined,
  listing: IbkrListingFlags | null | undefined,
): string | null {
  if (!shortEnabled) return SHORTABILITY_SHORT_DISABLED;
  if (!listing) return SHORTABILITY_NOT_SHORTABLE;
  if (listing.stale) return SHORTABILITY_STALE;
  const state = resolveShortabilityState(listing);
  // Explicit false only — missing orderable (legacy payloads) still OK when state is est.
  if (state !== 'shortable_est' || listing.orderable === false) {
    return SHORTABILITY_NOT_SHORTABLE;
  }
  return null;
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
  listingIbkr = null,
  onOrderPlaced,
}: Props) {
  const ibkrStatus = useIbkrStatus();
  const { topOfBook } = useTopOfBook();
  const initial = applyTicketDefaults(symbol, referencePrice, topOfBook);
  const [side, setSide] = useState<ManualOrderSide>(initial.side);
  const [shortEntry, setShortEntry] = useState(false);
  const [orderType, setOrderType] = useState<ManualOrderType>(initial.orderType);
  const shortBlockReason = shortDisabledReason(
    ibkrStatus.short_enabled,
    listingIbkr,
  );
  const [quantityMode, setQuantityMode] = useState<QuantityMode>('shares');
  const [quantityValue, setQuantityValue] = useState(initial.quantityValue);
  const [limitPrice, setLimitPrice] = useState(initial.limitPrice);
  const [stopPrice, setStopPrice] = useState(initial.stopPrice);
  const [outsideRth, setOutsideRth] = useState(initial.outsideRth);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [sessionUnlocked, setSessionUnlocked] = useState(readTicketSessionUnlocked);
  const [confirmSummary, setConfirmSummary] = useState<string | null>(null);
  const [pinDialogOpen, setPinDialogOpen] = useState(false);

  useEffect(() => {
    const sync = () => setSessionUnlocked(readTicketSessionUnlocked());
    sync();
    return subscribeTicketSessionUnlock(sync);
  }, []);

  const displayQuantityMode: QuantityMode = QTY_LOCKED ? 'shares' : quantityMode;
  const displayQuantityValue = QTY_LOCKED
    ? String(FORCED_QTY)
    : quantityValue;

  useEffect(() => {
    const next = applyTicketDefaults(symbol, referencePrice, topOfBook);
    setSide(next.side);
    setShortEntry(false);
    setOrderType(next.orderType);
    setQuantityMode('shares');
    setQuantityValue(next.quantityValue);
    setLimitPrice(next.limitPrice);
    setStopPrice(next.stopPrice);
    setOutsideRth(next.outsideRth);
    setResult(null);
    setConfirmSummary(null);
  }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  function selectDirection(nextShort: boolean) {
    if (nextShort && shortBlockReason) return;
    setShortEntry(nextShort);
    const nextSide: ManualOrderSide = nextShort ? 'SELL' : 'BUY';
    setSide(nextSide);
    const seeded = seedPricesForSide(
      nextSide,
      orderType,
      symbol,
      referencePrice,
      topOfBook,
    );
    if (orderType === 'LMT') setLimitPrice(seeded.limitPrice);
    if (orderType === 'STP') setStopPrice(seeded.stopPrice);
    setResult(null);
  }

  useEffect(() => {
    if (referencePrice != null && !limitPrice && orderType === 'LMT') {
      const seeded = seedPricesForSide(
        side,
        'LMT',
        symbol,
        referencePrice,
        topOfBook,
      );
      setLimitPrice(seeded.limitPrice);
    }
  }, [referencePrice, limitPrice, orderType, side, symbol, topOfBook]);

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

  function fail(text: string, reasonCode?: string | null) {
    setResult({ ok: false, text });
    notifyOrderRejected({ message: text, reasonCode });
  }

  async function executeOrder() {
    if (!connected || submitting) return;
    if (spendLocked) {
      fail('Orders remain locked by Nova environment safety settings.', 'ORDERS_GATE');
      return;
    }
    const timing = beginBrowserExecutionTiming(
      'manual_place',
      captureBrowserAction('user_action'),
    );

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
        shortEntry,
      },
      {
        marketReferencePrice: referencePrice,
        buyingPower: summary?.BuyingPower ?? null,
        positionQty: position?.qty ?? null,
      },
    );
    if (!built.ok) {
      fail(built.error);
      return;
    }

    setSubmitting(true);
    setResult(null);
    try {
      const response = await placeIbkrOrder(
        built.payload,
        undefined,
        { timing, referencePrice },
      );
      if (response.ok) {
        setResult({
          ok: true,
          text: `Order #${response.order_id} placed (${response.mode ?? mode})`,
        });
        onOrderPlaced?.(response);
      } else {
        fail(response.error ?? 'Order failed', response.reason_code);
      }
    } catch (error) {
      fail(executionTransportError(error));
    } finally {
      setSubmitting(false);
    }
  }

  function requestPlaceOrder() {
    if (!connected || submitting) return;
    if (spendLocked) {
      fail('Orders remain locked by Nova environment safety settings.', 'ORDERS_GATE');
      return;
    }

    if (shortEntry && shortBlockReason) {
      fail(shortBlockReason);
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
        shortEntry,
      },
      {
        marketReferencePrice: referencePrice,
        buyingPower: summary?.BuyingPower ?? null,
        positionQty: position?.qty ?? null,
      },
    );
    if (!built.ok) {
      fail(built.error);
      return;
    }

    const priceText =
      orderType === 'LMT'
        ? ` @ $${limitPrice}`
        : orderType === 'STP'
          ? ` stop $${stopPrice}`
          : '';
    const hoursText = outsideRth ? ' including extended hours' : ' during regular hours';
    const dirText = shortEntry ? 'SHORT' : side;
    const summaryText =
      `${dirText} ${built.quantity} ${symbol.toUpperCase()} (${orderType}${priceText})` +
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
        shortEntry={shortEntry}
        shortDisabledReason={shortBlockReason}
        onDirectionChange={selectDirection}
        onSideChange={setSide}
        onOrderTypeChange={selectOrderType}
        onQuantityModeChange={selectQuantityMode}
        onQuantityValueChange={onQuantityValueChange}
        onLimitPriceChange={setLimitPrice}
        onStopPriceChange={setStopPrice}
        onOutsideRthChange={setOutsideRth}
      />

      <ManualOrderFooter
        isPaper={mode === 'paper'}
        needsPinUnlock={needsPinUnlock}
        connected={connected}
        submitting={submitting}
        spendLocked={spendLocked}
        quantityLocked={QTY_LOCKED}
        forcedQty={FORCED_QTY}
        sessionUnlocked={sessionUnlocked}
        result={result}
        confirmSummary={confirmSummary}
        pinDialogOpen={pinDialogOpen}
        onConfirmClose={() => setConfirmSummary(null)}
        onConfirmPlace={() => void executeOrder()}
        onPinSubmit={submitPin}
        onPinClose={() => setPinDialogOpen(false)}
      />
    </form>
  );
}
