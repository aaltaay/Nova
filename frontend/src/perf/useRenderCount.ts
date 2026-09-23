/**
 * Count this component's renders for the window's performance report
 * (ADR 026). Deliberately no state and no effect: it bumps a counter while
 * rendering, so it adds no commit of its own. A development build's
 * StrictMode renders twice; the production desk counts each render once.
 */
import { countRender } from './perfCounters';

export function useRenderCount(name: string): void {
  countRender(name);
}
