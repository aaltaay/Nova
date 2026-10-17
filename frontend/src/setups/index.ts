/** Public setup-scanner API -- cross-feature imports use this barrel (ADR 005). */

export { useSetupsBoard, SetupsStreamProvider } from './SetupsStreamContext';
export { SetupsPanel } from './SetupsPanel';
export { SetupsTabCount } from './SetupsTabCount';
export { useSetupRows, type SetupStoreRow } from './useSetupRows';
export { useSetupsScoreboard } from './useSetupsScoreboard';
export { shortStageOf, stageSetupTicket, stageVenueLock } from './stageSetupTicket';
export { isShortRow } from './shortWords';
export { etHms, isRecordedBoard, recordedEmptyText, simBoardLine, simBoardTip } from './simBoardWords';
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
export { gradeLabel, gradeWords, pillarCount, type PillarCount } from './pillarWords';
/** Too thin to trade (2026-10-01): the reading off the wire, its words and its chip. */
export {
  isThin,
  liquidityTip,
  money as liquidityMoney,
  normalizeLiquidity,
  thinChip,
  type LiquidityRead,
} from './liquidity';
/** The one dismissed list the alert card and the Bots inbox share (ADR 042 draft). */
export {
  dismiss as dismissProposals,
  dismissedProposals,
  isDismissed as isProposalDismissed,
  subscribe as subscribeDismissedProposals,
} from './proposalDismissals';
/** What a proposal means for the operator's Stage: Nova takes it, not a trade, the size and the lock. */
export {
  notATradeText,
  proposalNotATrade,
  proposalStageLock,
  proposalStageSize,
  proposalTakenBy,
  proposalVerdictLine,
  stageLimit,
  type StageSize,
  type TakenBy,
} from './proposalVerdict';
/** The venue sleeve's risk per trade: the Trader plan and every proposal's Stage size by it. */
export {
  parseRiskUsd,
  riskSourceWords,
  saveSleeveRisk,
  useSleeveRisk,
  venueOrNull,
  VENUE_NAMES,
  type SleeveRisk,
  type SleeveVenue,
} from './sleeveRisk';
export { TF5_TRIAL_NOTE, tf5Words, type Tf5Tone } from './tf5Words';
/** The target menu (#845): target 1, target 2 and the share sold at target 1, with the words each came from. */
export {
  normalizeTargetFields,
  normalizeTargets,
  targetSentence,
  targetShare,
  type SetupTargets,
  type TargetFields,
  type TargetLeg,
  type TargetRule,
  type TargetStop,
} from './targets';
export type {
  Scoreboard,
  SetupCounts,
  SetupProposal,
  SetupRow,
  SetupSide,
  SetupsBoard,
  SetupState,
  SetupSummary,
  SetupType,
  ShortTest,
  SsrState,
  TapeRead,
  TapeVerdict,
} from './types';
