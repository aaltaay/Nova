import { useEffect, useState } from 'react';
import {
  forcedManualOrderQty,
  presetsForQuantityMode,
  usesLimitPrice,
  usesStopPrice,
  type ManualOrderType,
  type QuantityMode,
} from './orderEntry';
import { useTopOfBook } from '../hotkeys/TopOfBookContext';
import type { IbkrListingFlags } from '../types/ticker';
import { applyTicketDefaults, seedPricesForSide } from './applyTicketDefaults';
import { ManualOrderFields } from './ManualOrderFields';
import { ManualOrderFooter } from './ManualOrderFooter';
import { ManualOrderTicketHeader } from './ManualOrderTicketHeader';
import { useMarketOrdersRefused } from './marketOutsideRth';
import { ManualOrderLegsNote } from './ManualOrderLegsNote';
import { shortDisabledReason } from './shortDisabledReason';
import {
  allowShortSide,
  clampTicketSide,
  orderSideToTicketSide,
  ticketSideToOrder,
  type TicketSide,
} from './ticketSide';
import { subscribeOrderTicketPrefill } from './orderTicketPrefill';
import type { PlaceOrderResult } from './placeOrder';
import { evaluateTradingAllowed } from './tradingAllowed';
import {
  readTicketSessionUnlocked,
  subscribeTicketSessionUnlock,
  tryUnlockTicketSession,
} from './ticketUnlock';
import type { IbkrAccountSummary, IbkrMode, IbkrPosition } from './types';
import { useCompactTicket } from './useCompactTicket';
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
  const allowShort = allowShortSide(summary);
  const [ticketSide, setTicketSide] = useState<TicketSide>(() =>
    clampTicketSide(orderSideToTicketSide(initial.side), allowShort),
  );
  const { side, shortEntry } = ticketSideToOrder(ticketSide);
  const [orderType, setOrderType] = useState<ManualOrderType>(initial.orderType);
  const shortBlockReason = shortDisabledReason(
    ibkrStatus.short_enabled,
    listingIbkr,
    mode,
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
  const displayQuantityValue = QTY_LOCKED ? String(FORCED_QTY) : quantityValue;
  const ticketValues = {
    symbol,
    side,
    shortEntry,
    orderType,
    quantityMode: displayQuantityMode,
    quantityValue: displayQuantityValue,
    limitPrice,
    stopPrice,
    outsideRth,
    referencePrice,
    summary,
    position,
  };
  const { tif, selectTif, cost, practice } = useCompactTicket({ mode, ...ticketValues });
  const trading = evaluateTradingAllowed({
    connected,
    spendStatus,
    spendReason: ibkrStatus.spend_locked_reason,
    sessionUnlocked,
    backendAllowed: ibkrStatus.trading_allowed,
    backendReason: ibkrStatus.trading_allowed_reason,
  });
  const spendLocked = trading.blockers.includes('spend');
  const spendLockNote = trading.blockers.includes('spend') ? trading.reason : null;
  const needsPinUnlock = trading.blockers.includes('pin');
  const {
    submitting,
    result,
    confirmSummary,
    legsNote,
    legsBlocked,
    submit,
    executeOrder,
    setConfirmSummary,
    resetSubmission,
  } = useManualOrderSubmission({
    ...ticketValues,
    mode,
    connected,
    spendLocked,
    needsPinUnlock,
    shortBlockReason,
    onNeedsPin: () => setPinDialogOpen(true),
    onOrderPlaced,
  });

  useEffect(() => {
    const next = applyTicketDefaults(symbol, referencePrice, topOfBook);
    setTicketSide(orderSideToTicketSide(next.side));
    setOrderType(next.orderType);
    setQuantityMode('shares');
    setQuantityValue(next.quantityValue);
    setLimitPrice(next.limitPrice);
    setStopPrice(next.stopPrice);
    setOutsideRth(next.outsideRth);
    resetSubmission();
  }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  // The chart menu stages an order here; the PIN / spend / confirm gates still own the place.
  useEffect(() => {
    return subscribeOrderTicketPrefill(symbol, (req) => {
      setTicketSide(orderSideToTicketSide(req.side));
      setOrderType(req.orderType);
      setQuantityMode('shares');
      if (!QTY_LOCKED) setQuantityValue(req.quantityValue);
      setLimitPrice(req.limitPrice);
      resetSubmission();
    });
  }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => setTicketSide((current) => clampTicketSide(current, allowShort)), [allowShort]);

  function selectTicketSide(next: TicketSide) {
    if (next === 'short' && (!allowShort || shortBlockReason)) return;
    setTicketSide(next);
    const mapped = ticketSideToOrder(next);
    const seeded = seedPricesForSide(
      mapped.side,
      orderType,
      symbol,
      referencePrice,
      topOfBook,
    );
    if (usesLimitPrice(orderType)) setLimitPrice(seeded.limitPrice);
    if (usesStopPrice(orderType)) setStopPrice(seeded.stopPrice);
    resetSubmission();
  }

  useEffect(() => {
    if (referencePrice != null && !limitPrice && usesLimitPrice(orderType)) {
      const seeded = seedPricesForSide(
        side,
        orderType,
        symbol,
        referencePrice,
        topOfBook,
      );
      setLimitPrice(seeded.limitPrice);
    }
  }, [referencePrice, limitPrice, orderType, side, symbol, topOfBook]);

  function selectOrderType(next: ManualOrderType) {
    setOrderType(next);
    const seeded = seedPricesForSide(
      side,
      next,
      symbol,
      referencePrice,
      topOfBook,
    );
    if (usesLimitPrice(next)) setLimitPrice(seeded.limitPrice);
    if (usesStopPrice(next)) setStopPrice(seeded.stopPrice);
    resetSubmission();
  }

  // MKT_OUTSIDE_RTH: the default order type is Market, and after the close
  // the backend refuses it -- move to Limit before the operator can Place.
  const marketBlockedReason = useMarketOrdersRefused(mode);
  useEffect(() => {
    if (marketBlockedReason && orderType === 'MKT') selectOrderType('LMT');
  }, [marketBlockedReason, orderType]); // eslint-disable-line react-hooks/exhaustive-deps

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
      <ManualOrderTicketHeader
        symbol={symbol}
        mode={mode}
        tif={tif}
        disabled={submitting}
        onTifChange={selectTif}
      />
      <ManualOrderFields
        symbol={symbol}
        topOfBook={topOfBook}
        cost={cost}
        ticketSide={ticketSide}
        allowShort={allowShort}
        orderType={orderType}
        quantityMode={displayQuantityMode}
        quantityValue={displayQuantityValue}
        limitPrice={limitPrice}
        stopPrice={stopPrice}
        outsideRth={outsideRth}
        disabled={!connected || submitting}
        quantityLocked={QTY_LOCKED}
        shortDisabledReason={shortBlockReason}
        marketDisabledReason={marketBlockedReason}
        onTicketSideChange={selectTicketSide}
        onOrderTypeChange={selectOrderType}
        onQuantityModeChange={selectQuantityMode}
        onQuantityValueChange={onQuantityValueChange}
        onLimitPriceChange={setLimitPrice}
        onStopPriceChange={setStopPrice}
        onOutsideRthChange={setOutsideRth}
      />

      <ManualOrderLegsNote note={legsNote} blocked={legsBlocked} />

      <ManualOrderFooter
        isPaper={mode === 'paper'}
        practice={practice}
        ticketSide={ticketSide}
        symbol={symbol}
        needsPinUnlock={needsPinUnlock}
        connected={connected}
        submitting={submitting}
        spendLocked={spendLocked}
        spendLockReason={spendLockNote}
        spendDisarmed={spendStatus === 'locked_disarmed'}
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
