import { describe, expect, it } from 'vitest';
import { QUOTE_PANEL_COLLAPSED_STORAGE_KEY } from '../constantGroups/scanner_board';
import { readQuotePanelCollapsed, writeQuotePanelCollapsed } from './useQuotePanelCollapsed';

function memory(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (k: string) => (k in data ? data[k] : null),
    setItem: (k: string, v: string) => { data[k] = v; },
  };
}

describe('quote panel collapse persistence', () => {
  it('round-trips under one versioned key', () => {
    const store = memory();
    writeQuotePanelCollapsed(true, store);
    expect(JSON.parse(store.data[QUOTE_PANEL_COLLAPSED_STORAGE_KEY])).toEqual({ v: 1, collapsed: true });
    expect(readQuotePanelCollapsed(store)).toBe(true);
    writeQuotePanelCollapsed(false, store);
    expect(readQuotePanelCollapsed(store)).toBe(false);
  });

  it('reads anything it does not recognise as expanded, the default', () => {
    expect(readQuotePanelCollapsed(memory())).toBe(false);
    expect(readQuotePanelCollapsed(memory({ [QUOTE_PANEL_COLLAPSED_STORAGE_KEY]: '{"v":2,"collapsed":true}' }))).toBe(false);
    expect(readQuotePanelCollapsed(memory({ [QUOTE_PANEL_COLLAPSED_STORAGE_KEY]: 'not json' }))).toBe(false);
    expect(readQuotePanelCollapsed(null)).toBe(false);
  });
});
