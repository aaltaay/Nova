/** Public Sim API — cross-feature imports must use this barrel (ADR 005). */

export { useSimReplayDesk } from './useSimReplayDesk';
export { simClockResource } from './simClockResource';
export { SIM_FOCUS_RAIL_REPLAY_NOTE } from './simConstants';
// ADR 050: an agent's show / move lands the Sim through the same requests as its panels.
export { LandingStopped, landSim, moveSim } from './simLanding';
export type { Landed, LandingHooks, LandingWindow, SimLandingPlan, SimMovePlan } from './simLanding';
