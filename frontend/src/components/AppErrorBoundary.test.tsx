/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppErrorBoundary } from './AppErrorBoundary';
import { APP_SHELL_RELOAD_SESSION_KEY } from './appErrorRecovery';

vi.mock('../utils/reportClientError', () => ({
  reportClientError: vi.fn(),
}));

function Boom({ message }: { message: string }): never {
  throw new Error(message);
}

describe('AppErrorBoundary', () => {
  let container: HTMLDivElement;
  let root: Root;
  let consoleError: typeof console.error;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    consoleError = console.error;
    console.error = vi.fn();
    sessionStorage.clear();
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    console.error = consoleError;
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('soft-retries non-fatal errors without reloading', async () => {
    const reload = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, reload },
    });

    await act(async () => {
      root.render(
        <AppErrorBoundary source="dashboard">
          <Boom message="chart boom" />
        </AppErrorBoundary>,
      );
    });
    expect(container.textContent).toMatch(/Something went wrong/);
    expect(container.querySelector('button')?.textContent).toMatch(/Retry/);
    expect(reload).not.toHaveBeenCalled();
  });

  it('auto-reloads once on missing WorkspaceProvider', async () => {
    vi.useFakeTimers();
    const reload = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, reload },
    });

    await act(async () => {
      root.render(
        <AppErrorBoundary source="dashboard">
          <Boom message="useWorkspace must be used within WorkspaceProvider" />
        </AppErrorBoundary>,
      );
    });

    expect(sessionStorage.getItem(APP_SHELL_RELOAD_SESSION_KEY)).toBe('1');
    expect(container.textContent).toMatch(/Recovering/);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(reload).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
