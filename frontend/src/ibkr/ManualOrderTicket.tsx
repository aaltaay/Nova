import { useEffect, useState } from 'react';
import {
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
import { subscribeOrderTicketPrefill } from './orderTicketPrefill';
import type { PlaceOrderResult } from './placeOrder';
import { resolveShortabilityState } from './ShortabilityChip';
import { isSpendLocked, spendLockReason } from './spendLock';
import {
  readTicketSessionUnlocked,
  subscribeTicketSessionUnlock,
  tryUnlockTicketSession,
} from './ticketUnlock';
import type { IbkrAccountSummary, IbkrMode, IbkrPosition } from './types';
import { useManualOrderSubmission } from './useManualOrderSubmission';
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
  const [sessionUnlocked, setSessionUnlocked] = useState(readTicketSessionUnlocked);
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
  const spendLocked = isSpendLocked(spendStatus);
  const spendLockNote = spendLockReason(
    spendStatus,
    ibkrStatus.spend_locked_reason,
  );
  const needsPinUnlock = !sessionUnlocked;
  const {
    submitting,
    result,
    confirmSummary,
    submit,
    executeOrder,
    setConfirmSummary,
    resetSubmission,
  } = useManualOrderSubmission({
    symbol,
    mode,
    connected,
    spendLocked,
    needsPinUnlock,
    side,
    shortEntry,
    shortBlockReason,
    orderType,
    quantityMode: displayQuantityMode,
    quantityValue: displayQuantityValue,
    limitPrice,
    stopPrice,
    outsideRth,
    referencePrice,
    summary,
    position,
    onNeedsPin: () => setPinDialogOpen(true),
    onOrderPlaced,
  });

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
    resetSubmission();
  }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  // Chart context menu stages an order here instead of placing one -- the PIN,
  // spend-lock and confirm gates below stay the only way an order leaves Nova.
  useEffect(() => {
    return subscribeOrderTicketPrefill(symbol, (req) => {
      setSide(req.side);
      setShortEntry(false);
      setOrderType(req.orderType);
      setQuantityMode('shares');
      if (!QTY_LOCKED) setQuantityValue(req.quantityValue);
      setLimitPrice(req.limitPrice);
      if (req.orderType !== 'LMT') setOutsideRth(false);
      resetSubmission();
    });
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
    resetSubmission();
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

  function selectOrderType(next: ManualOrderType) {
    setOrderType(next);
    if (next !== 'LMT') setOutsideRth(false);
    resetSubmission();
  }

  function selectQuantityMode(next: QuantityMode) {
    if (QTY_LOCKED) return;
    setQuantityMode(next);
    setQuantityValue(String(presetsForQuantityMode(next)[0]));
    resetSubmission();
  }

  function onQuantityValueChange(next: string) {
    if (QTY_LOCKED) return;
    setQuantityValue(next);
  }

  function submitPin(pin: string): boolean {
    const ok = tryUnlockTicketSession(pin);
    if (ok) {
      setSessionUnlocked(true);
      resetSubmission();
      setPinDialogOpen(false);
    }
    return ok;
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
        spendLockReason={spendLockNote}
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
