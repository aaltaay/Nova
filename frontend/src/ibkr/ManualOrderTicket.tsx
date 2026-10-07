import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import {
  forcedManualOrderQty,
  presetsForQuantityMode,
  usesLimitPrice,
  usesStopPrice,
  type ManualOrderType,
  type QuantityMode,
} from './orderEntry';
import { useTopOfBook } from '../hotkeys/TopOfBookContext';
import { useViewLock } from '../market_view';
import { TICKET_WHY_SENDING } from '../constantGroups/trader_chrome';
import { TRADE_DEFAULTS_WAITING } from '../constantGroups/trade_defaults';
import type { IbkrListingFlags } from '../types/ticker';
import { applyTicketDefaults, seedFollow, seedPricesForSide } from './applyTicketDefaults';
import { ManualOrderFields } from './ManualOrderFields';
import { ManualOrderFooter } from './ManualOrderFooter';
import { GATEWAY_STATUS_KNOWN, gatewayLockWhy, type GatewayStatusFact } from './gatewayStatusWording';
import { ManualOrderTicketHeader } from './ManualOrderTicketHeader';
import { useMarketOrdersRefused } from './marketOutsideRth';
import { ManualOrderLegsNote } from './ManualOrderLegsNote';
import { shortDisabledReason } from './shortDisabledReason';
import { ShortCheckBox } from './ShortCheckBox';
import {
  allowShortSide,
  clampTicketSide,
  orderSideToTicketSide,
  ticketSideToOrder,
  type TicketSide,
} from './ticketSide';
import type { PlaceOrderResult } from './placeOrder';
import { evaluateTradingAllowed } from './tradingAllowed';
import {
  readTicketSessionUnlocked,
  subscribeTicketSessionUnlock,
} from './ticketUnlock';
import type { IbkrAccountSummary, IbkrMode, IbkrPosition } from './types';
import type { QuickPriceKind } from './ticketPriceQuick';
import { useCompactTicket } from './useCompactTicket';
import { useTicketPriceFollow } from './useTicketPriceFollow';
import { useManualOrderSubmission } from './useManualOrderSubmission';
import { useIbkrStatus } from './useIbkrStatus';
import { useTradingPinGate } from './useTradingPinGate';
import { useVenuePrice } from '../sim/useReplayQuote';
import { getConfirmedDeskVenueSnapshot, subscribeConfirmedDeskVenue } from './confirmedDeskVenue';
import { useTradeDefaultsPrefs } from '../settings';
import { useTicketDefaultsSync } from './useTicketDefaultsSync';
import { useShortTicket } from './useShortTicket';
import { useTicketSideActions } from './useTicketSideActions';

interface Props {
  symbol: string;
  mode: IbkrMode;
  connected: boolean;
  /** Whether `connected: false` is a status answer or an unknown (QA D10, #459). */
  gatewayStatus?: GatewayStatusFact;
  spendStatus?: string;
  summary: IbkrAccountSummary | null;
  position: IbkrPosition | null;
  referencePrice: number | null;
  listingIbkr?: IbkrListingFlags | null;
  onOrderPlaced?: (result: PlaceOrderResult) => void;
  /**
   * Another action's outcome for the Last line -- the rail's Flatten, whose
   * own footer the rail hides (QA R32). `seq` changes with each new outcome.
   */
  externalResult?: { ok: boolean; text: string; seq: number } | null;
}

const FORCED_QTY = forcedManualOrderQty();
const QTY_LOCKED = FORCED_QTY != null;

export function ManualOrderTicket({
  symbol,
  mode,
  connected,
  gatewayStatus = GATEWAY_STATUS_KNOWN,
  spendStatus,
  summary,
  position,
  referencePrice: livePrice,
  listingIbkr = null,
  onOrderPlaced,
  externalResult = null,
}: Props) {
  const ibkrStatus = useIbkrStatus();
  const { venue, generation } = useSyncExternalStore(subscribeConfirmedDeskVenue, getConfirmedDeskVenueSnapshot);
  const prefs = useTradeDefaultsPrefs(venue);
  const { topOfBook } = useTopOfBook();
  const viewLockWhy = useViewLock(symbol);  // ADR 045: Level 2 behind the market locks Place
  // Only this symbol's live book prices a Market order's Cost (R36).
  const liveBook = topOfBook && topOfBook.symbol.toUpperCase() === symbol.trim().toUpperCase()
    ? { bid: topOfBook.bid, ask: topOfBook.ask }
    : null;
  // Sim off the live edge prices from the replay at the playhead, never the live feed (R10 / V24).
  const { price: referencePrice, note: priceNote, bid: quoteBid, ask: quoteAsk } = useVenuePrice(symbol, livePrice, liveBook);
  const initial = applyTicketDefaults(venue, symbol, referencePrice, topOfBook);
  const allowShort = allowShortSide(summary);
  const [ticketSide, setTicketSide] = useState<TicketSide>(() =>
    clampTicketSide(orderSideToTicketSide(initial.side), allowShort),
  );
  const { side, shortEntry } = ticketSideToOrder(ticketSide);
  const [orderType, setOrderType] = useState<ManualOrderType>(initial.orderType);
  const shortBlockReason = shortDisabledReason(ibkrStatus.short_enabled, listingIbkr, mode, ibkrStatus.short_proof);
  const [quantityMode, setQuantityMode] = useState<QuantityMode>('shares');
  const [quantityValue, setQuantityValue] = useState(initial.quantityValue);
  const [limitPrice, setLimitPrice] = useState(initial.limitPrice);
  const [stopPrice, setStopPrice] = useState(initial.stopPrice);
  const [outsideRth, setOutsideRth] = useState(initial.outsideRth);
  // The padlock is the backend arm latch (ADR 018); one flow unlocks it for every door.
  const sessionUnlocked = useSyncExternalStore(subscribeTicketSessionUnlock, readTicketSessionUnlocked, () => false);
  const { ensureUnlocked, pinDialog } = useTradingPinGate();

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
  // ADR 048: the sides follow the position, and a short carries its Buy stop and the short check.
  const short = useShortTicket({
    symbol, summary, position, allowShort, shortBlock: shortBlockReason, ticketSide, orderType, limitPrice, topOfBook,
    quantityMode: displayQuantityMode, quantityValue: displayQuantityValue, stopOffset: prefs.shortStopOffset,
  });
  const { tif, selectTif, cost, practice } = useCompactTicket({
    venue, mode, ...ticketValues, priceNote, quote: { bid: quoteBid, ask: quoteAsk },
  });
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
    cancelConfirm,
    showResult,
  } = useManualOrderSubmission({
    ...ticketValues,
    venue,
    mode,
    connected,
    spendLocked,
    needsPinUnlock,
    shortBlockReason,
    buyStop: short.buyStop,
    buyStopRefusal: short.stopRefusal,
    qtyCap: ibkrStatus.qty_cap ?? null,
    // Place while locked unlocks and stops there: the operator presses Place again.
    onNeedsPin: () => {
      void ensureUnlocked().then((ok) => {
        if (ok) resetSubmission();
      });
    },
    onOrderPlaced,
  });
  // The limit follows the side of the Level 2 book it was taken from, and
  // holds while a confirm is open or an order is in flight.
  const priceFollow = useTicketPriceFollow({
    symbol,
    book: topOfBook,
    initial: seedFollow(venue, initial.side, initial.orderType),
    active: usesLimitPrice(orderType),
    frozen: submitting || confirmSummary != null,
    setLimitPrice,
  });
  // MASTER TEST QTY GATE (#444): say the sent size whenever the typed size is
  // above the door's cap, so the ticket never shows a size it will not send.
  // The cap binds Live only; Paper and Sim report null and stay quiet.
  const qtyCap = ibkrStatus.qty_cap ?? null;
  const typedShares =
    displayQuantityMode === 'shares' ? Number(displayQuantityValue) : NaN;
  const qtyCapNote =
    qtyCap != null && Number.isFinite(typedShares) && typedShares > qtyCap
      ? `Live cap: this order sends ${qtyCap} of ${typedShares} shares.`
      : null;

  useTicketDefaultsSync({
    symbol, venue, generation, prefs, side, orderType, referencePrice, topOfBook,
    setTicketSide, setOrderType, setQuantityMode, setQuantityValue,
    setLimitPrice, setStopPrice, setOutsideRth, setFollowing: priceFollow.setFollowing, resetSubmission,
  });

  // A confirm built on one venue is never sent on another: it names the old
  // account, and Confirm would place it wherever the desk points now.
  useEffect(() => {
    resetSubmission();
  }, [mode]); // eslint-disable-line react-hooks/exhaustive-deps

  // Choosing a side seeds its prices; a staged order lands on its side; a side the position locks gives way.
  const selectTicketSide = useTicketSideActions({
    venue, symbol, ticketSide, orderType, referencePrice, topOfBook, quantityLocked: QTY_LOCKED, short,
    setTicketSide, setOrderType, setQuantityMode, setQuantityValue, setLimitPrice, setStopPrice,
    setFollowing: priceFollow.setFollowing, resetSubmission, cancelConfirm, say: showResult,
  });

  // The rail's Flatten reports here: its own footer is hidden in the rail (QA R32).
  useEffect(() => {
    if (externalResult) showResult({ ok: externalResult.ok, text: externalResult.text });
  }, [externalResult?.seq]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (referencePrice != null && !limitPrice && usesLimitPrice(orderType)) {
      const seeded = seedPricesForSide(
        venue,
        side,
        orderType,
        symbol,
        referencePrice,
        topOfBook,
      );
      setLimitPrice(seeded.limitPrice);
    }
  }, [referencePrice, limitPrice, orderType, side, symbol, topOfBook, venue]);

  function selectOrderType(next: ManualOrderType) {
    setOrderType(next);
    const seeded = seedPricesForSide(
      venue,
      side,
      next,
      symbol,
      referencePrice,
      topOfBook,
    );
    if (usesLimitPrice(next)) setLimitPrice(seeded.limitPrice);
    priceFollow.setFollowing(seedFollow(venue, side, next));
    if (usesStopPrice(next)) setStopPrice(seeded.stopPrice);
    resetSubmission();
  }

  /** A typed price is the operator's own: the limit stops following the book. */
  function typeLimitPrice(next: string) {
    priceFollow.setFollowing(null);
    setLimitPrice(next);
  }

  function followBook(kind: QuickPriceKind | null, price: string | null) {
    priceFollow.setFollowing(kind);
    if (price != null) setLimitPrice(price);
  }

  // MKT_OUTSIDE_RTH: the default order type is Market, and after the close
  // the backend refuses it -- move to Limit before the operator can Place.
  const marketBlockedReason = useMarketOrdersRefused(mode);
  useEffect(() => {
    if (marketBlockedReason && orderType === 'MKT') selectOrderType('LMT');
  }, [marketBlockedReason, orderType]); // eslint-disable-line react-hooks/exhaustive-deps

  // Stable, so the quantity row skips the renders a new price causes (#707); resetSubmission touches
  // only refs and setters, so its latest copy is the one to call.
  const resetSubmissionRef = useRef(resetSubmission);
  resetSubmissionRef.current = resetSubmission;
  const selectQuantityMode = useCallback((next: QuantityMode) => {
    if (QTY_LOCKED) return;
    setQuantityMode(next);
    setQuantityValue(String(presetsForQuantityMode(next)[0]));
    resetSubmissionRef.current();
  }, []);

  const onQuantityValueChange = useCallback((next: string) => {
    if (QTY_LOCKED) return;
    setQuantityValue(next);
  }, []);

  // Every locked field says why (ux/whyTip.ts).
  const fieldsWhy = !connected ? gatewayLockWhy(gatewayStatus) : submitting ? TICKET_WHY_SENDING : null;

  return (
    <form className="manual-order-ticket" onSubmit={submit}>
      <ManualOrderTicketHeader
        symbol={symbol}
        mode={mode}
        tif={tif}
        disabled={submitting || venue === null}
        why={venue === null ? TRADE_DEFAULTS_WAITING : TICKET_WHY_SENDING}
        onTifChange={selectTif}
      />
      <ManualOrderFields
        symbol={symbol}
        topOfBook={topOfBook}
        priceFollowing={priceFollow.following}
        onPriceFollow={followBook}
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
        why={fieldsWhy}
        quantityLocked={QTY_LOCKED}
        shortDisabledReason={shortBlockReason}
        sideButtons={short.buttons}
        sideNote={short.note}
        buyStop={short.buyStop}
        buyStopRefusal={short.stopRefusal}
        onBuyStopChange={short.setBuyStop}
        limitNote={short.limitNote}
        shortMargin={short.margin}
        marketDisabledReason={marketBlockedReason}
        onTicketSideChange={selectTicketSide}
        onOrderTypeChange={selectOrderType}
        onQuantityModeChange={selectQuantityMode}
        onQuantityValueChange={onQuantityValueChange}
        onLimitPriceChange={typeLimitPrice}
        onStopPriceChange={setStopPrice}
        onOutsideRthChange={setOutsideRth}
      />

      {ticketSide === 'short' && <ShortCheckBox state={short.check} />}

      <ManualOrderLegsNote note={legsNote} blocked={legsBlocked} />

      <ManualOrderFooter
        isPaper={mode === 'paper'}
        practice={practice}
        ticketSide={ticketSide}
        symbol={symbol}
        submitLabel={short.submitLabel}
        submitTone={short.submitTone}
        needsPinUnlock={needsPinUnlock}
        connected={connected}
        gatewayStatus={gatewayStatus}
        submitting={submitting}
        viewLockWhy={viewLockWhy}
        spendLocked={spendLocked}
        spendLockReason={spendLockNote}
        spendDisarmed={spendStatus === 'locked_disarmed'}
        quantityLocked={QTY_LOCKED}
        forcedQty={FORCED_QTY}
        qtyCapNote={qtyCapNote}
        sessionUnlocked={sessionUnlocked}
        result={result}
        confirmSummary={confirmSummary}
        onConfirmClose={() => setConfirmSummary(null)}
        onConfirmPlace={() => void executeOrder()}
      />
      {pinDialog}
    </form>
  );
}
