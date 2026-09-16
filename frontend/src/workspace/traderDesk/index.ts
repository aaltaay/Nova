export { createTraderDeskBus } from './bus';
export { allowTraderTabDrop, startTraderTabDrag, takeForeignTraderTabDrop } from './domDrag';
export {
  canExtractFromDesk,
  claimDockTarget,
  closePolicyAfterGive,
  deskRoleFromStockView,
  isForeignTabDrag,
} from './commands';
export {
  TRADER_DESK_CHANNEL,
  TRADER_DESK_STORAGE_KEY,
  TRADER_DESK_PROTOCOL_V,
  TRADER_TAB_DRAG_MIME,
  dataTransferHasTraderTab,
  parseTraderTabDrag,
  readTraderTabDrag,
  writeTraderTabDrag,
  type TraderDeskRole,
  type TraderTabDragPayload,
} from './protocol';
export {
  initialTraderState,
  readStoredTabs,
  writeBlockNotice,
  writeStoredTabs,
} from './traderSession';
export { useTraderDeskBinding } from './useTraderDeskBinding';
export { useTraderDesk, type TraderDockOffer } from './useTraderDesk';
export { getTraderWindowId } from './windowId';
