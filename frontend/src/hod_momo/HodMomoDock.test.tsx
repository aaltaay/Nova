/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HOD_MOMO_ALERT_SOUND_KEY } from './hodMomoAlertSoundConstants';
import { resetHodMomoAlertSoundForTests } from './hodMomoAlertSound';
import { HOD_MOMO_STRIP_ROW_PX, HOD_MOMO_STRIP_STORAGE_KEY } from './hodMomoStripConstants';
import { HodMomoDock } from './HodMomoDock';
import type { HodMomoContextValue } from './HodMomoContext';
import { HodMomoContextProvider } from './HodMomoContext';
import type { AlertObject } from './types';

const workspaceMock = {
  selectedSymbol: 'ABC' as string | null,
  setSelectedSymbol: vi.fn(),
  selectRowSymbol: vi.fn(),
  openStockView: vi.fn(),
};

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => workspaceMock,
}));

vi.mock('../sample_data/SampleDataContext', () => ({
  useSampleDataOptional: () => null,
}));

const integrityMock = { report: null as unknown, error: null as string | null, status: 'pass' };
vi.mock('./useHodMomoIntegrity', () => ({
  useHodMomoIntegrity: () => integrityMock,
}));

vi.mock('./HodMomoDebugPanel', () => ({
  HodMomoDebugPanel: () => <div data-testid="hod-debug-stub" />,
}));

vi.mock('./HodMomoSettings', () => ({
  HodMomoSettings: () => <div data-testid="hod-settings-stub" />,
}));

function alert(over: Partial<AlertObject> & { id: string }): AlertObject {
  return {
    timestamp: '2026-09-22T12:39:52Z',
    ticker: 'GRML',
    strategy_id: 7,
    strategy_name: 'Low Float - High Rel Vol',
    price: 12.81,
    change_pct: 33.3,
    rvol: 6.4,
    rvol_5min: null,
    float_shares: 8_200_000,
    gap_pct: null,
    volume: 4_820_000,
    momentum_pct: null,
    rvol_source: 'yfinance',
    consolidation_count: 1,
    consolidated_ids: [],
    ...over,
  };
}

const ALERTS: AlertObject[] = [
  alert({ id: 'n1', ticker: 'GRML', timestamp: '2026-09-22T12:39:52Z' }),
  alert({ id: 'n2', ticker: 'BRNQ', strategy_id: 11, strategy_name: 'Squeeze Alert - Up 5% in 5min', timestamp: '2026-09-22T12:37:10Z', price: 6.42 }),
  alert({ id: 'n3', ticker: 'QNME', strategy_id: 12, strategy_name: 'Running Up Alert', timestamp: '2026-09-22T12:33:45Z' }),
];

function makeValue(overrides: Partial<HodMomoContextValue> = {}): HodMomoContextValue {
  return {
    stream: { alerts: ALERTS, totalToday: ALERTS.length, connected: true },
    config: {
      state: { loaded: true, strategies: {}, master: { consolidation_sec: 5 } } as unknown as HodMomoContextValue['config']['state'],
      updateStrategy: () => {},
      updateMaster: () => {},
      resetStrategy: async () => {},
      resetAll: async () => {},
    },
    hodCount: 2,
    runningUpCount: 1,
    dockMode: 'hod_momo',
    setDockMode: vi.fn(),
    collapsed: false,
    setCollapsed: vi.fn(),
    toggleCollapsed: vi.fn(),
    rows: 4,
    setRows: vi.fn(),
    focusDock: vi.fn(),
    showHodSettings: false,
    setShowHodSettings: vi.fn(),
    toggleHodSettings: vi.fn(),
    ...overrides,
  };
}

function renderStrip(value: HodMomoContextValue, props: Parameters<typeof HodMomoDock>[0] = {}) {
  return render(
    <HodMomoContextProvider value={value}>
      <HodMomoDock {...props} />
    </HodMomoContextProvider>,
  );
}

function pointer(type: string, clientY: number): Event {
  return new MouseEvent(type, { clientY, button: 0, bubbles: true, cancelable: true });
}

describe('HodMomoDock (strip)', () => {
  beforeEach(() => {
    localStorage.removeItem(HOD_MOMO_STRIP_STORAGE_KEY);
    localStorage.removeItem(HOD_MOMO_ALERT_SOUND_KEY);
    resetHodMomoAlertSoundForTests();
    workspaceMock.selectRowSymbol.mockReset();
    workspaceMock.openStockView.mockReset();
    workspaceMock.setSelectedSymbol.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders one 22px line per HOD alert, newest on top, with the gate values it carries', () => {
    renderStrip(makeValue());
    const rows = screen.getAllByTestId('hod-momo-strip-row');
    expect(rows).toHaveLength(2); // the Running Up alert is on the other segment
    expect(rows[0].getAttribute('data-symbol')).toBe('GRML');
    expect(rows[1].getAttribute('data-symbol')).toBe('BRNQ');
    expect(rows[0].textContent).toContain('12.81');
    expect(rows[0].textContent).toContain('Low Float - High Rel Vol');
    expect(rows[0].textContent).toContain('S7');
    expect(rows[0].textContent).toContain('6.4×');
    expect(rows[0].textContent).toContain('8.2M');
    expect(rows[0].textContent).toContain('rvol5m —');
    expect(screen.getByTestId('hod-momo-dock-body').style.height).toBe(`${4 * HOD_MOMO_STRIP_ROW_PX}px`);
    expect(screen.getByTestId('hod-momo-strip-since').textContent).toMatch(/^2 alerts since \d{2}:\d{2}$/);
    expect(screen.getByTestId('hod-momo-strip-integrity').textContent).toContain('integrity ok');
  });

  it('shows Running Up alerts on that segment', () => {
    const setDockMode = vi.fn();
    renderStrip(makeValue({ setDockMode }));
    fireEvent.click(screen.getByTestId('hod-momo-dock-mode-ru'));
    expect(setDockMode).toHaveBeenCalledWith('running_up');
    cleanup();
    renderStrip(makeValue({ dockMode: 'running_up' }));
    const rows = screen.getAllByTestId('hod-momo-strip-row');
    expect(rows).toHaveLength(1);
    expect(rows[0].getAttribute('data-symbol')).toBe('QNME');
  });

  it('row click selects the symbol; the ticker opens Trader', () => {
    renderStrip(makeValue());
    const rows = screen.getAllByTestId('hod-momo-strip-row');
    fireEvent.click(rows[1]);
    expect(workspaceMock.selectRowSymbol).toHaveBeenCalledWith('BRNQ');
    expect(workspaceMock.openStockView).not.toHaveBeenCalled();
    fireEvent.click(rows[0].querySelector('button.symbol-btn') as HTMLElement);
    expect(workspaceMock.openStockView).toHaveBeenCalledWith('GRML');
  });

  it('routes a row click through onAlertSelect when the page provides it', () => {
    const onAlertSelect = vi.fn();
    renderStrip(makeValue(), { onAlertSelect });
    fireEvent.click(screen.getAllByTestId('hod-momo-strip-row')[0]);
    expect(onAlertSelect).toHaveBeenCalledWith('GRML');
    expect(workspaceMock.selectRowSymbol).not.toHaveBeenCalled();
  });

  it('folds to its header line', () => {
    const toggleCollapsed = vi.fn();
    renderStrip(makeValue({ collapsed: true, toggleCollapsed }));
    expect(screen.queryByTestId('hod-momo-dock-body')).toBeNull();
    expect(screen.queryByTestId('hod-momo-strip-grip')).toBeNull();
    expect(screen.getByTestId('hod-momo-strip-since')).toBeTruthy();
    fireEvent.click(screen.getByTestId('hod-momo-dock-toggle'));
    expect(toggleCollapsed).toHaveBeenCalledTimes(1);
  });

  it('drags the bottom edge and snaps the height to whole rows', () => {
    const setRows = vi.fn();
    renderStrip(makeValue({ rows: 4, setRows }));
    const grip = screen.getByTestId('hod-momo-strip-grip');
    act(() => { grip.dispatchEvent(pointer('pointerdown', 100)); });
    act(() => { grip.dispatchEvent(pointer('pointermove', 100 + 2 * HOD_MOMO_STRIP_ROW_PX + 3)); });
    expect(setRows).toHaveBeenLastCalledWith(6);
    act(() => { grip.dispatchEvent(pointer('pointermove', 100 - 10 * HOD_MOMO_STRIP_ROW_PX)); });
    expect(setRows).toHaveBeenLastCalledWith(1);
    act(() => { grip.dispatchEvent(pointer('pointerup', 100)); });
    fireEvent.doubleClick(grip);
    expect(setRows).toHaveBeenLastCalledWith(4);
  });

  it('flags an alert that arrives after mount as NEW, never the snapshot', () => {
    const value = makeValue();
    const { rerender } = renderStrip(value);
    expect(screen.queryAllByTestId('hod-momo-strip-row').some((r) => r.getAttribute('data-new') === '1')).toBe(false);
    const arrived = alert({ id: 'live-1', ticker: 'NUVT', timestamp: '2026-09-22T12:41:00Z' });
    rerender(
      <HodMomoContextProvider value={{ ...value, stream: { ...value.stream, alerts: [arrived, ...ALERTS] } }}>
        <HodMomoDock />
      </HodMomoContextProvider>,
    );
    const rows = screen.getAllByTestId('hod-momo-strip-row');
    expect(rows[0].getAttribute('data-symbol')).toBe('NUVT');
    expect(rows[0].getAttribute('data-new')).toBe('1');
    expect(rows[0].textContent).toContain('NEW');
    expect(rows[1].getAttribute('data-new')).toBeNull();
  });

  it('keeps sound, strategies, clear and configure behind the header menu', () => {
    const toggleHodSettings = vi.fn();
    renderStrip(makeValue({ toggleHodSettings }));
    expect(screen.queryByTestId('hod-momo-strip-menu')).toBeNull();
    fireEvent.click(screen.getByTestId('hod-momo-strip-more'));
    expect(screen.getByTestId('hod-momo-strip-menu')).toBeTruthy();
    expect(screen.getByTestId('hod-momo-sound-toggle')).toBeTruthy();
    expect(screen.getByTestId('hod-momo-dock-clear')).toBeTruthy();
    // Hiding strategy 7 removes the GRML row and leaves BRNQ (strategy 11).
    const strategies = screen.getByTestId('hod-momo-strip-strategies');
    const labels = Array.from(strategies.querySelectorAll('label'));
    const s7 = labels.find((el) => el.querySelector('.hod-strip__menu-name')?.textContent === 'Low Float - High Rel Vol');
    fireEvent.click(s7?.querySelector('input') as HTMLInputElement);
    expect(screen.getAllByTestId('hod-momo-strip-row').map((r) => r.getAttribute('data-symbol'))).toEqual(['BRNQ']);
    fireEvent.click(screen.getByTestId('hod-momo-dock-configure'));
    expect(toggleHodSettings).toHaveBeenCalled();
    expect(screen.queryByTestId('hod-momo-strip-menu')).toBeNull();
  });

  it('folds strategies one ticker fired together into one row with a count bubble named on hover', () => {
    const at = Date.parse('2026-09-22T12:45:00Z') / 1000;
    const together: AlertObject[] = [
      alert({ id: 'm7', ticker: 'MSS', created_ts: at }),
      alert({ id: 'm10', ticker: 'MSS', strategy_id: 10, strategy_name: 'Squeeze Alert - Up 10% in 10min', created_ts: at, momentum_pct: 34.5 }),
      alert({ id: 'm11', ticker: 'MSS', strategy_id: 11, strategy_name: 'Squeeze Alert - Up 5% in 5min', created_ts: at - 2, momentum_pct: 31.9 }),
    ];
    const value = makeValue();
    renderStrip({
      ...value,
      stream: { ...value.stream, alerts: [...together, ...ALERTS] },
      config: {
        ...value.config,
        state: { ...value.config.state, strategies: { 10: { color: '#f97316' } } } as unknown as HodMomoContextValue['config']['state'],
      },
    });
    const rows = screen.getAllByTestId('hod-momo-strip-row');
    expect(rows.map((r) => r.getAttribute('data-symbol'))).toEqual(['MSS', 'GRML', 'BRNQ']);
    expect(rows[0].getAttribute('data-strategies')).toBe('3');
    expect(screen.getByTestId('hod-momo-strip-bubble').textContent).toBe('3');
    expect(rows[0].textContent).toContain('S7');
    expect(rows[0].textContent).toContain('S10');
    expect(rows[0].textContent).toContain('S11');
    expect(rows[0].textContent).toContain('+31.9%–+34.5%');
    expect(screen.getByTestId('hod-momo-strip-since').textContent).toMatch(/^5 alerts since/);
    expect(screen.getByTestId('hod-momo-dock-body').getAttribute('data-row-count')).toBe('3');

    expect(screen.queryByTestId('hod-momo-strip-card')).toBeNull();
    fireEvent.mouseEnter(screen.getByTestId('hod-momo-strip-group'));
    const card = screen.getByTestId('hod-momo-strip-card');
    expect(card.getAttribute('role')).toBe('tooltip');
    expect(card.textContent).toContain('MSS · 3 strategies at');
    const cardRows = screen.getAllByTestId('hod-momo-strip-card-row');
    expect(cardRows.map((r) => r.querySelector('.hod-strip__card-name')?.textContent)).toEqual([
      'Low Float - High Rel Vol',
      'Squeeze Alert - Up 10% in 10min',
      'Squeeze Alert - Up 5% in 5min',
    ]);
    expect(cardRows[1].textContent).toContain('momo +34.5%');
    // S11 was raised two seconds before the row's time: its own clock is named.
    expect(cardRows[2].querySelector('.hod-strip__card-detail')?.textContent).toMatch(/\d{2}:\d{2}:\d{2}$/);
    expect((cardRows[1].querySelector('.hod-strip__card-dot') as HTMLElement).style.background).toBeTruthy();
    fireEvent.mouseLeave(screen.getByTestId('hod-momo-strip-group'));
    expect(screen.queryByTestId('hod-momo-strip-card')).toBeNull();
  });

  it('states an empty feed instead of showing nothing', () => {
    renderStrip(makeValue({ stream: { alerts: [], totalToday: 0, connected: false } }));
    expect(screen.getByTestId('hod-momo-strip-empty').textContent).toContain('Connecting');
  });
});
