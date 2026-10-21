/** Public heat map API (ADR 061) -- cross-feature imports must use this barrel (ADR 005). */

export { HeatMapView } from './HeatMapView';
export { HeatMapToolbar, useHeatMapShown } from './HeatMapToolbar';
export { noteHeatBeat, noteHeatBook, noteHeatLine, noteHeatPrint, resetHeat } from './heatStore';
export { noteHeatWatch } from './heatWatch';
export { HEAT_LINE_LENT } from './heatMapConstants';
