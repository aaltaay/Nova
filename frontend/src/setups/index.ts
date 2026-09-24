/** Public setup-scanner API -- cross-feature imports use this barrel (ADR 005). */

export { useSetupsBoard, SetupsStreamProvider } from './SetupsStreamContext';
export { useSetupRows } from './useSetupRows';
export { stageSetupTicket } from './stageSetupTicket';
export { fmtCents, fmtPct, fmtPx, fmtR, isActionable, stagedLimit, tapeRank } from './setupsFormat';
export {
  ALL_SETUPS,
  consumeSetupsBoardOpen,
  getSetupsFilter,
  requestSetupsBoard,
  setSetupsFilter,
  subscribeSetupsBoardOpen,
  useSetupsFilter,
} from './setupsBoardFilter';
export {
  etHm,
  FIRST_PULLBACK,
  funnelSteps,
  gradeWords,
  lastWords,
  otherSetups,
  rowRank,
  rowsBySymbol,
  setupLabel,
  setupShort,
  setupTypeOf,
  signedPct,
  stateWords,
  tapeWords,
  toGoWords,
  triggerWords,
  windowWords,
  type FunnelStep,
  type Words,
} from './setupWords';
export type {
  Scoreboard,
  SetupCounts,
  SetupProposal,
  SetupRow,
  SetupsBoard,
  SetupState,
  SetupSummary,
  SetupType,
  TapeRead,
  TapeVerdict,
} from './types';
