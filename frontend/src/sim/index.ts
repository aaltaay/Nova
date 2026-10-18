/** Public Sim API — cross-feature imports must use this barrel (ADR 005). */

export { isReplayDesk, useSimReplayDesk, useSimReplayPlayhead } from './useSimReplayDesk';
export { simClockResource } from './simClockResource';
export type { SimClockState } from './simClockTypes';
export {
  SIM_CHART_REFRESH_MS,
  SIM_CLOCK_SCRUB_EVENT,
  matchesSimClockScrub,
} from './simClockEvents';
export {
  SIM_CAPTURE_TAPE_NOT_RECORDED,
  SIM_CAPTURE_TAPE_TITLE,
  SIM_FOCUS_RAIL_REPLAY_NOTE,
  SIM_REPLAY_TAPE_STATUS,
} from './simConstants';
// ADR 050: an agent's show / move lands the Sim through the same requests as its panels.
export { LandingStopped, landSim, moveSim } from './simLanding';
export type { Landed, LandingHooks, LandingWindow, SimLandingPlan, SimMovePlan } from './simLanding';
// The scanner's quote panel on a Sim desk: the same rule and empty quote as a Trader tab. The notice
// component itself is not exported here -- it pulls the workspace, and the chart imports this barrel.
export { useSimReplayTarget } from './useSimReplayTarget';
export { simRailNote, simVenueTagState } from './simReplayTarget';
export {
  captureQuoteDetail,
  historicalQuoteDetail,
  replayFactsNoteForDetail,
  sessionDateFromStamp,
  simEmptyQuoteDetail,
} from './historicalQuoteDetail';
export { etTime } from './historicalReplayFormat';
export { clockWindow } from './simStripFormat';
export {
  finiteOrNull,
  isObject,
  objects,
  text,
  textOrNull,
  type Obj,
} from './payloadGuards';
export { replayPollResource, type ReplayResourceState } from './replayPollResource';
// Its replay quote and company facts off the live edge (operator report, 2026-10-12).
export { replayPanelDetail } from './replayPanelDetail';
export { useHistoricalSnapshot } from './useHistoricalSnapshot';
// A tab's price off the live edge is the replay's at the playhead: the plan box's price tick reads it too.
export { marketFillPrice, useReplayQuote, useVenuePrice } from './useReplayQuote';
// A rebuilt day's Gappers by the second asks the leaderboard routes the way replay reads do (ADR 023 amendment 2026-10-13).
export { replayPost, replayRequest } from './replayRequest';
export { CaptureReplayL2Chip } from './CaptureReplayChip';
