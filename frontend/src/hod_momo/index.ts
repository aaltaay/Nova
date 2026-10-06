/** Public HOD Momo API — cross-feature imports must use this barrel (ADR 005). */

export { HodMomoTab } from './HodMomoTab';
export { RunningUpTab } from './RunningUpTab';
export { HodMomoSettings } from './HodMomoSettings';
export { HodMomoSection } from './HodMomoSection';
export { HodMomoDock } from './HodMomoDock';
export { HodMomoProvider } from './HodMomoProvider';
export { HodMomoFixtureProvider } from './HodMomoFixtureProvider';
export { useHodMomo, useHodMomoOptional } from './HodMomoContext';
export type { HodDockMode, HodMomoContextValue } from './HodMomoContext';
export {
  isAlertDockMode,
  isRosterDockMode,
  SCANNER_DOCK_ROSTER_MODES,
} from './scannerDockModes';
export {
  isRunningUpStrategy,
  partitionScannerAlerts,
} from './scannerPartition';
export { subscribeHodMomoLiveAlerts } from './hodMomoLiveAlerts';
export { fmtStripClock, stripAlertMs } from './hodMomoStripRows';
// The HOD rows every view draws (the Scanner's strip, the Trader's Focus rail half).
export { HodMomoStripRow } from './HodMomoStripRow';
export { groupIsNew } from './hodMomoStripGroups';
export { HOD_MOMO_STRIP_EMPTY_CONNECTING } from './hodMomoStripConstants';
export { useHodStripView } from './useHodStripView';
export type { HodStripView } from './useHodStripView';
export type { AlertObject } from './types';
