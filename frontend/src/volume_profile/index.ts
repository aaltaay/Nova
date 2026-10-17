/** Public volume-profile API (ADR 058) -- cross-feature imports must use this barrel (ADR 005). */

export { VolumeProfileChartLayer } from './VolumeProfileChartLayer';
export { VolumeProfileToolbar } from './VolumeProfileToolbar';
export { buildProfile } from './volumeProfile';
export type { ProfileBar, VolumeProfile } from './volumeProfile';
export { profileToWire } from './volumeProfileApi';
export type { ProfileKind, VolumeProfileWire } from './volumeProfileApi';
