/** Public IBKR UI API — cross-feature imports must use this barrel (ADR 005). */

export { DepthLadder, MontageSide } from './DepthLadder';
export type { DepthMarker } from './depthMarkers';
export { bookPeak } from './dasDepthTiers';
export { TimeSalesPanel } from './TimeSalesPanel';
export { TimeSalesView } from './TimeSalesView';
export type { TapePrint, TapeState } from './tapeFeed';
export { cancelIbkrOrderWithFeedback } from './cancelOrder';
export { useIbkrStatus, type IbkrClientStatus } from './useIbkrStatus';
export { useIbkrAccount } from './useIbkrAccount';
export {
  getIbkrStatusSnapshot,
  refreshIbkrStatusNow,
  subscribeIbkrStatus,
} from './ibkrStatusPoller';
export {
  getConfirmedDeskVenueSnapshot, isConfirmedDeskVenueSnapshotCurrent,
  subscribeConfirmedDeskVenue, useConfirmedDeskVenue,
} from './confirmedDeskVenue';
export type { ConfirmedDeskVenueSnapshot } from './confirmedDeskVenue';
export { deskVenueOf, practiceLedgerReachable, resolveDeskVenue } from './deskVenue';
export { lastKnownAsOfMessage, lastKnownBanner } from './disconnectCopy';
export { watchDeskRequestRoute } from './deskRequestRouteFence';
// ADR 050: an agent's show moves the desk through the same door as the venue pills.
export { moveDeskToVenue, switchDeskVenue } from './deskVenueSwitch';
export { defaultTicketQty } from './applyTicketDefaults';
export { formatSeedPrice } from './tradeDefaultSeed';
export {
  claimDeskPollLeader, heartbeatDeskPollLeader, publishDeskPollSnap,
  readDeskPollSnap, subscribeDeskPollSnap,
} from './deskSharedPoll';
export { useTradingPinGate } from './useTradingPinGate';
export { simPlayhead, venueClockNow } from './marketOutsideRth';
export { etMinutesNow, shouldUseOutsideRth } from './extendedSession';
export { flattenSpendLockReason, isDisarmed, spendStatusLabel } from './spendLock';
export { readTicketSessionUnlocked } from './ticketUnlock';
export { evaluateTradingAllowed } from './tradingAllowed';
export type { GatewayStatusFact } from './gatewayStatusWording';
export { useOrderTicketListening } from './useOrderTicketListening';
export { requestOrderTicketPrefill, type OrderTicketPrefill } from './orderTicketPrefill';
export type { ManualOrderSide } from './orderEntry';
// ADR 048: the Short / Cover hotkeys send through the one order helper; Level 2's short chips read the facts.
export {
  cancelAllOrdersForSymbol,
  cancelAllWorkingOrders,
  countOpenWorkingOrders,
  placeIbkrOrder,
  type PlaceOrderResult,
} from './placeOrder';
export {
  buildBuyMarketShares,
  buildExitFullPosition,
  buildExitPositionPercent,
  buildLongExitPercent,
} from './exitPosition';
export { closeFullPosition } from './closeFullPosition';
export { planFlattenExit } from './planFlattenExit';
export { confirmAndFillWorkingOrder } from './fillWorkingOrderImmediately';
export { newGestureKey } from './gestureKey';
export { notifyOrderRejected } from './notifyOrderRejected';
export { readSkipPlaceConfirm, writeSkipPlaceConfirm } from './placeConfirmPrefs';
export { useShortFacts } from './shortFacts';
export { useShortCheck } from './shortCheck';
export type { ShortCheckRule, ShortCheckState } from './shortCheck';
export { flattenLabel, liquidationTitle } from './orderSide';
export { SentByTd } from './SentByCell';
export { OrderSideTd, PositionSideTd } from './OrderSideCell';
export { FillLatencyTd } from './FillLatencyCell';
export { OrderTableColumnHeader, OrderTableDnd } from './OrderTableColumnHeader';
export { orderSentBy } from './orderSentBy';
export { commissionCellTitle, formatCommission } from './orderCommission';
export {
  formatOrderDateTime,
  formatOrderSide,
  formatOrderStatus,
  formatOrderType,
  orderActivityIso,
  orderFilledTimeTitle,
  orderSideClass,
  orderSideRowClass,
  orderStatusTone,
  orderSubmittedIso,
  orderSubmittedTimeTitle,
  plausiblePrice,
} from './orderDisplay';
export { displayFilledQty, practiceFillTitle } from './orderFillHonesty';
export { orderRowKeys, uniqueOrders } from './orderIdentity';
export { normalizeOrderList } from './orderRowNormalize';
export {
  CLOSED_COLUMN_META,
  DEFAULT_CLOSED_ORDER_COLUMNS,
  normalizeColumnOrder,
  type ClosedOrderColumnId,
} from './orderTableColumns';
export { sortOrders } from './orderTableSort';
export { useOrderTableColumnOrder } from './useOrderTableColumnOrder';
export { useOrderTableSort } from './useOrderTableSort';
export { buildMockWorkingOrders, samplePriceAt } from './mockWorkingOrders';
export { GatewayDoorTrail } from './GatewayDoorTrail';
export { HaltEtaChip } from './HaltEtaChip';
export { ShortabilityChip } from './ShortabilityChip';
export { WorkingOrdersPanel } from './WorkingOrdersPanel';
// ADR 044 decision 6: who holds each Level 2 line, the loans, and the lending switch.
export { fetchDepthLines, loanFor, normalizeDepthLines, setDepthLending } from './depthLines';
export type {
  DepthLine, DepthLineHolder, DepthLinesView, DepthLoan, DepthLoanEnded, LoanTapeState,
} from './depthLines';
export { depthLentText, tapeLentText } from './lentWords';
// ADR 047 amendment (2026-10-12): the day's LULD band, step by step, for the 1-minute chart.
export { fmtBand } from './luld';
export { readLuldTrail } from './luldTrail';
export type { LuldStep, LuldTrail } from './luldTrail';
export type {
  AutoRecordStatus,
  DepthLevel,
  IbkrAccountSummary,
  IbkrMode,
  IbkrOrder,
  IbkrPosition,
  IbkrStatus,
  RecordingStopped,
} from './types';
// The desk says each fill out loud (desk-ops.md, "The desk's voice and the header mute").
export { FillVoiceHost } from './FillVoiceHost';
