/**
 * @vitest-environment jsdom
 */
import { fireEvent } from '@testing-library/react';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SENSORS_EMPTY_CATALOG, SENSORS_LOAD_ERROR } from '../constantGroups/sensors';
import { SensorBoard } from './SensorBoard';

const fetchCatalog = vi.fn();
const fetchSnapshot = vi.fn();

vi.mock('../api/sensorApi', () => ({
  fetchSensorCatalog: (...args: unknown[]) => fetchCatalog(...args),
  fetchSensorSnapshot: (...args: unknown[]) => fetchSnapshot(...args),
}));

vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => ({ mode: 'paper', connected: true }),
}));

const catalog = {
  count: 3,
  sensors: [
    { id: 1, sensor: 'l2', title: 'L2 book', path: '/sensors/l2', status: 'live', needs_symbol: true },
    { id: 16, sensor: 'memory', title: 'Brain memory', path: '/sensors/memory', status: 'stub', needs_symbol: true },
    { id: 17, sensor: 'regime', title: 'Regime', path: '/sensors/regime', status: 'computed_stub', needs_symbol: true },
  ],
};

function snap(symbol = 'AAPL') {
  return {
    symbol,
    count: 3,
    sensors: [
      { sensor: 'l2', symbol, status: 'live', as_of: 1, data: { imbalance: 0.2, spread_ticks: 1 } },
      { sensor: 'memory', symbol, status: 'stub', as_of: 1, data: { count: 0 } },
      { sensor: 'regime', symbol, status: 'computed_stub', as_of: 1, data: { regime: 'unknown', confidence: 0.1 } },
    ],
  };
}

describe('SensorBoard', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    fetchCatalog.mockReset();
    fetchSnapshot.mockReset();
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('renders live / stub / computed stub chips and values', async () => {
    fetchCatalog.mockResolvedValue(catalog);
    fetchSnapshot.mockResolvedValue(snap());
    await act(async () => {
      root.render(<SensorBoard />);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="sensor-chip-live"]')?.textContent).toMatch(/live/i);
    expect(container.querySelector('[data-testid="sensor-chip-stub"]')?.textContent).toMatch(/stub/i);
    expect(container.querySelector('[data-testid="sensor-chip-computed_stub"]')?.textContent).toMatch(/computed/i);
    expect(container.querySelector('[data-testid="sensor-value-l2"]')?.textContent).toContain('imb');
    expect(container.querySelector('[data-testid="sensor-title-l2"]')?.textContent).toBe('L2 book');
    expect(container.querySelector('[data-testid="sensor-title-memory"]')?.textContent).toBe('Brain memory');
    expect(container.querySelector('[data-testid="sensor-symbol"]')).toBeTruthy();
  });

  it('refreshes snapshot for a typed symbol', async () => {
    fetchCatalog.mockResolvedValue(catalog);
    fetchSnapshot.mockResolvedValue(snap());
    await act(async () => {
      root.render(<SensorBoard />);
    });
    await act(async () => {
      await Promise.resolve();
    });
    const input = container.querySelector('[data-testid="sensor-symbol"]');
    expect(input).toBeTruthy();
    await act(async () => {
      fireEvent.change(input as HTMLInputElement, { target: { value: 'msft' } });
      fireEvent.submit(container.querySelector('form') as HTMLFormElement);
    });
    expect(fetchSnapshot).toHaveBeenCalledWith('MSFT');
  });

  it('shows a loud error when the snapshot fails', async () => {
    fetchCatalog.mockResolvedValue(catalog);
    fetchSnapshot.mockRejectedValue(new Error(SENSORS_LOAD_ERROR));
    await act(async () => {
      root.render(<SensorBoard />);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="sensor-board-error"]')?.textContent).toContain(
      SENSORS_LOAD_ERROR,
    );
  });

  it('shows empty catalog loudly', async () => {
    fetchCatalog.mockResolvedValue({ count: 0, sensors: [] });
    fetchSnapshot.mockResolvedValue({ symbol: 'AAPL', count: 0, sensors: [] });
    await act(async () => {
      root.render(<SensorBoard />);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="sensor-board-empty"]')?.textContent).toBe(
      SENSORS_EMPTY_CATALOG,
    );
  });
});
