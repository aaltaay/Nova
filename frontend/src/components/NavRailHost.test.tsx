/**
 * @vitest-environment jsdom
 *
 * QA V33: after the last Trader tab popped out, the main window showed the Desk
 * with "No symbol open" while the rail still highlighted Trader.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const workspace = {
  traderTabs: [] as string[],
  traderViewActive: true,
  openStockView: vi.fn(),
  closeTraderView: vi.fn(),
  showScannerView: vi.fn(),
};
const seen: Array<{ traderActive: boolean }> = [];

vi.mock('../workspace/WorkspaceContext', () => ({ useWorkspace: () => workspace }));
vi.mock('../settings/SettingsContext', () => ({ useSettingsOptional: () => null }));
vi.mock('./NavRail', () => ({
  NavRail: (props: { traderActive: boolean }) => {
    seen.push({ traderActive: props.traderActive });
    return null;
  },
}));

import { NavRailHost } from './NavRailHost';

describe('NavRailHost', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    seen.length = 0;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('does not highlight Trader once its last tab has popped out (QA V33)', () => {
    workspace.traderTabs = [];
    workspace.traderViewActive = true;
    act(() => root.render(<NavRailHost />));
    expect(seen.at(-1)?.traderActive).toBe(false);
  });

  it('highlights Trader while a Trader tab is up', () => {
    workspace.traderTabs = ['GRML'];
    workspace.traderViewActive = true;
    act(() => root.render(<NavRailHost />));
    expect(seen.at(-1)?.traderActive).toBe(true);
    workspace.traderViewActive = false;
    act(() => root.render(<NavRailHost key="off" />));
    expect(seen.at(-1)?.traderActive).toBe(false);
  });
});
