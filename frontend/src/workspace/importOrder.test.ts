/**
 * #639: the module registry reaches the nav-rail store through a cycle (registry -> modules ->
 * QuoteHeaderPanel -> the workspace barrel -> navRailStore -> registry). A page that loads the
 * registry first -- the E2E fixture pages do -- must still load: nothing in the store may read the
 * registry while the store itself is loading.
 */
import { describe, expect, it } from 'vitest';
import { DEFAULT_ACTIVE_TAB } from './registry';
import { getNavRailSnapshot } from './navRailStore';

describe('workspace import order', () => {
  it('loads the registry before the nav-rail store without a use-before-define', () => {
    expect(DEFAULT_ACTIVE_TAB).toBe('gappers');
    expect(getNavRailSnapshot().scanner.activeTab).toBe('gappers');
  });
});
