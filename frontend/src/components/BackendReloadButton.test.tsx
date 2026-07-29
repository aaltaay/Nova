/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BackendReloadButton } from './BackendReloadButton';

const confirmAppMock = vi.fn();
const startLocalApiMock = vi.fn();

vi.mock('../ux', () => ({
  confirmApp: (...args: unknown[]) => confirmAppMock(...args),
}));

vi.mock('../utils/startLocalApi', () => ({
  startLocalApi: (...args: unknown[]) => startLocalApiMock(...args),
}));

describe('BackendReloadButton', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    confirmAppMock.mockReset();
    startLocalApiMock.mockReset();
    confirmAppMock.mockResolvedValue(true);
    startLocalApiMock.mockResolvedValue({ ok: true, mode: 'vite-dev' });
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('asks for confirmation then restarts the local API', async () => {
    const onReloaded = vi.fn();
    act(() => {
      root.render(<BackendReloadButton onReloaded={onReloaded} />);
    });

    const btn = container.querySelector('[data-testid="backend-reload-btn"]') as HTMLButtonElement;
    expect(btn.textContent).toBe('Reload backend');

    await act(async () => {
      btn.click();
      await Promise.resolve();
    });

    expect(confirmAppMock).toHaveBeenCalledOnce();
    expect(startLocalApiMock).toHaveBeenCalledOnce();
    expect(onReloaded).toHaveBeenCalledOnce();
  });

  it('does nothing when confirmation is cancelled', async () => {
    confirmAppMock.mockResolvedValue(false);
    act(() => {
      root.render(<BackendReloadButton />);
    });

    const btn = container.querySelector('[data-testid="backend-reload-btn"]') as HTMLButtonElement;
    await act(async () => {
      btn.click();
      await Promise.resolve();
    });

    expect(startLocalApiMock).not.toHaveBeenCalled();
  });
});
