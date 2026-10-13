/** Public Sim API — cross-feature imports must use this barrel (ADR 005). */

export { useSimReplayDesk } from './useSimReplayDesk';
export { simClockResource } from './simClockResource';
export { SIM_FOCUS_RAIL_REPLAY_NOTE } from './simConstants';
// ADR 050: an agent's show / move lands the Sim through the same requests as its panels.
export { LandingStopped, landSim, moveSim } from './simLanding';
export type { Landed, LandingHooks, LandingWindow, SimLandingPlan, SimMovePlan } from './simLanding';
// The scanner's quote panel on a Sim desk: the same rule and empty quote as a Trader tab. The notice
// component itself is not exported here -- it pulls the workspace, and the chart imports this barrel.
export { useSimReplayTarget } from './useSimReplayTarget';
export { simRailNote } from './simReplayTarget';
export { simEmptyQuoteDetail } from './historicalQuoteDetail';
// Its replay quote and company facts off the live edge (operator report, 2026-10-12).
export { replayPanelDetail } from './replayPanelDetail';
export { useHistoricalSnapshot } from './useHistoricalSnapshot';
