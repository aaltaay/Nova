/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  HOD_MOMO_DOCK_COLLAPSED_KEY,
  HOD_MOMO_DOCK_HEIGHT_KEY,
} from '../constants';
import {
  makeLiveScannerFeedStub,
  ScannerDataContextProvider,
} from '../scanner/ScannerDataContext';
import { HodMomoDock } from './HodMomoDock';
import type { HodMomoContextValue } from './HodMomoContext';
import { HodMomoContextProvider } from './HodMomoContext';

const workspaceMock = {
  selectedSymbol: 'ABC' as string | null,
  setSelectedSymbol: vi.fn(),
  openStockView: vi.fn(),
};

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => workspaceMock,
}));

vi.mock('../sample_data/SampleDataContext', () => ({
  useSampleDataOptional: () => null,
}));

vi.mock('./HodMomoSection', () => ({
  HodMomoSection: () => <div data-testid="hod-section-stub" />,
}));

function makeValue(overrides: Partial<HodMomoContextValue> = {}): HodMomoContextValue {
  return {
    stream: { alerts: [], totalToday: 0, connected: true },
    config: {
      state: { loaded: true } as HodMomoContextValue['config']['state'],
      updateStrategy: () => {},
      updateMaster: () => {},
      resetStrategy: async () => {},
      resetAll: async () => {},
    },
    hodCount: 3,
    runningUpCount: 1,
    dockMode: 'hod_momo',
    setDockMode: vi.fn(),
    collapsed: true,
    setCollapsed: vi.fn(),
    toggleCollapsed: vi.fn(),
    heightPx: 320,
    setHeightPx: vi.fn(),
    focusDock: vi.fn(),
    showHodSettings: false,
    setShowHodSettings: vi.fn(),
    toggleHodSettings: vi.fn(),
    ...overrides,
  };
}

function renderDock(value: HodMomoContextValue) {
  return render(
    <HodMomoContextProvider value={value}>
      <HodMomoDock />
    </HodMomoContextProvider>,
  );
}

describe('HodMomoDock', () => {
  beforeEach(() => {
    localStorage.removeItem(HOD_MOMO_DOCK_COLLAPSED_KEY);
    localStorage.removeItem(HOD_MOMO_DOCK_HEIGHT_KEY);
  });

  afterEach(() => {
    cleanup();
  });

  it('collapsed strip has no body; toggle expands', () => {
    const toggleCollapsed = vi.fn();
    renderDock(makeValue({ collapsed: true, toggleCollapsed }));
    expect(screen.queryByTestId('hod-momo-dock-body')).toBeNull();
    fireEvent.click(screen.getByTestId('hod-momo-dock-toggle'));
    expect(toggleCollapsed).toHaveBeenCalled();
  });

  it('expanded shows section and mode tabs', () => {
    const setDockMode = vi.fn();
    renderDock(makeValue({ collapsed: false, setDockMode }));
    expect(screen.getByTestId('hod-momo-dock-body')).toBeTruthy();
    expect(screen.getByTestId('hod-section-stub')).toBeTruthy();
    fireEvent.click(screen.getByTestId('hod-momo-dock-mode-ru'));
    expect(setDockMode).toHaveBeenCalledWith('running_up');
  });

  it('hides roster scanner pills when no scanner feed is mounted', () => {
    renderDock(makeValue({ collapsed: true }));
    expect(screen.queryByTestId('hod-momo-dock-mode-gappers')).toBeNull();
    expect(screen.queryByTestId('hod-momo-dock-mode-gainers')).toBeNull();
  });

  it('declares the restored dock table for L1 on mount, not just on click', () => {
    const setL1DockTab = vi.fn();
    render(
      <ScannerDataContextProvider value={makeLiveScannerFeedStub({ setL1DockTab })}>
        <HodMomoContextProvider value={makeValue({ collapsed: false, dockMode: 'gainers' })}>
          <HodMomoDock />
        </HodMomoContextProvider>
      </ScannerDataContextProvider>,
    );
    // A reload resets the main tab to frozen Gappers; without this the visible
    // dock Gainers roster would never get a price_patch.
    expect(setL1DockTab).toHaveBeenCalledWith('gainers');
  });

  it('clears the dock L1 table when showing an alert-only mode', () => {
    const setL1DockTab = vi.fn();
    render(
      <ScannerDataContextProvider value={makeLiveScannerFeedStub({ setL1DockTab })}>
        <HodMomoContextProvider value={makeValue({ collapsed: false, dockMode: 'hod_momo' })}>
          <HodMomoDock />
        </HodMomoContextProvider>
      </ScannerDataContextProvider>,
    );
    expect(setL1DockTab).toHaveBeenCalledWith(null);
  });

  it('shows roster pills and switches the dock body to that table', () => {
    const setDockMode = vi.fn();
    const setL1DockTab = vi.fn();
    render(
      <ScannerDataContextProvider
        value={makeLiveScannerFeedStub({ setL1DockTab })}
      >
        <HodMomoContextProvider
          value={makeValue({
            collapsed: false,
            dockMode: 'gappers',
            setDockMode,
          })}
        >
          <HodMomoDock />
        </HodMomoContextProvider>
      </ScannerDataContextProvider>,
    );
    expect(screen.getByTestId('hod-momo-dock-mode-gappers')).toBeTruthy();
    expect(screen.getByTestId('hod-momo-dock-mode-gainers')).toBeTruthy();
    expect(screen.getByTestId('hod-momo-dock-mode-losers')).toBeTruthy();
    expect(screen.getByTestId('hod-momo-dock-mode-afterhours')).toBeTruthy();
    expect(screen.getByTestId('hod-momo-dock-mode-catalysts')).toBeTruthy();
    expect(screen.getByTestId('hod-momo-dock-roster')).toBeTruthy();
    expect(screen.queryByTestId('hod-momo-dock-clear')).toBeNull();
    fireEvent.click(screen.getByTestId('hod-momo-dock-mode-gainers'));
    expect(setDockMode).toHaveBeenCalledWith('gainers');
    expect(setL1DockTab).toHaveBeenCalledWith('gappers');
  });
});

