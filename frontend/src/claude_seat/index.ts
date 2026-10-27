/** Claude's seat on the desk (ADR 068) -- cross-feature imports must use this barrel (ADR 005). */

export { ClaudeSeatPill } from './ClaudeSeatPill';
export { ClaudeSeatChartLayer } from './ClaudeSeatChartLayer';
export { ClaudeLineFrame } from './ClaudeLineFrame';
export { ClaudeLinesFullBox } from './ClaudeLinesFullBox';
export { ClaudeMark } from './ClaudeMark';
export { useClaudeSeat } from './claudeSeatStore';
export type { ClaudeSeatStatus } from './types';
