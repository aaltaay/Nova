/** Shared test-only window contract, imported by the fixture and the separate Playwright TS project. */
import type { HotListState } from '../../src/hot_list';
import type { ViewStamp } from '../../src/market_view';

export interface DeskFreezeFixtureHandle {
  metrics: { hotCommits: number; depthCommits: number };
  hotState: () => HotListState;
  stamp: () => ViewStamp;
  lock: () => string | null;
}

declare global {
  interface Window {
    deskFreezeFixture: DeskFreezeFixtureHandle;
  }
}
