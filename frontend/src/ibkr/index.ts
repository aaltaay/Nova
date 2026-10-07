/** Public IBKR UI API — cross-feature imports must use this barrel (ADR 005). */

export { DepthLadder, MontageSide } from './DepthLadder';
export type { DepthMarker } from './depthMarkers';
export { bookPeak } from './dasDepthTiers';
export { TimeSalesPanel } from './TimeSalesPanel';
export { TimeSalesView } from './TimeSalesView';
export type { TapePrint, TapeState } from './tapeFeed';
export { cancelIbkrOrderWithFeedback } from './cancelOrder';
export { useIbkrStatus } from './useIbkrStatus';
export {
  getConfirmedDeskVenueSnapshot, isConfirmedDeskVenueSnapshotCurrent,
  subscribeConfirmedDeskVenue, useConfirmedDeskVenue,
} from './confirmedDeskVenue';
export type { ConfirmedDeskVenueSnapshot } from './confirmedDeskVenue';
export { watchDeskRequestRoute } from './deskRequestRouteFence';
// ADR 050: an agent's show moves the desk through the same door as the venue pills.
export { moveDeskToVenue, switchDeskVenue } from './deskVenueSwitch';
export { defaultTicketQty } from './applyTicketDefaults';
export {
  claimDeskPollLeader, heartbeatDeskPollLeader, publishDeskPollSnap,
  readDeskPollSnap, subscribeDeskPollSnap,
} from './deskSharedPoll';
export { useTradingPinGate } from './useTradingPinGate';
export { simPlayhead } from './marketOutsideRth';
export { flattenSpendLockReason } from './spendLock';
export type { GatewayStatusFact } from './gatewayStatusWording';
export { useOrderTicketListening } from './useOrderTicketListening';
export { requestOrderTicketPrefill } from './orderTicketPrefill';
export { SentByTd } from './SentByCell';
export { OrderSideTd, PositionSideTd } from './OrderSideCell';
export { flattenLabel } from './orderSide';
export { orderSentBy } from './orderSentBy';
// ADR 044 decision 6: who holds each Level 2 line, the loans, and the lending switch.
export { fetchDepthLines, loanFor, normalizeDepthLines, setDepthLending } from './depthLines';
export type {
  DepthLine, DepthLineHolder, DepthLinesView, DepthLoan, DepthLoanEnded, LoanTapeState,
} from './depthLines';
export { depthLentText, tapeLentText } from './lentWords';
