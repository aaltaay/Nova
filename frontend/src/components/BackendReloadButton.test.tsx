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

const backend = vi.hoisted(() => ({
  tag: null as string | null,
  checkout: null as string | null,
  desk: 'v1024',
  /** What the backend answers once a restart lands (null: unchanged). */
  afterRestart: null as { tag: string; checkout: string } | null,
}));
vi.mock('../utils/backendReleaseTag', () => ({
  refreshBackendReleaseTag: async () => {},
  currentBackendReleaseTag: () => backend.tag,
  currentBackendCheckoutTag: () => backend.checkout,
}));
vi.mock('../utils/novaReleaseTag', () => ({
  novaRendererReleaseTag: () => backend.desk,
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
    startLocalApiMock.mockImplementation(async () => {
      if (backend.afterRestart) {
        backend.tag = backend.afterRestart.tag;
        backend.checkout = backend.afterRestart.checkout;
      }
      return { ok: true, mode: 'vite-dev' };
    });
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    backend.tag = null;
    backend.checkout = null;
    backend.afterRestart = null;
  });

  async function clickReload() {
    act(() => {
      root.render(<BackendReloadButton />);
    });
    await act(async () => {
      (container.querySelector('[data-testid="backend-reload-btn"]') as HTMLButtonElement).click();
      await Promise.resolve();
    });
  }

  it('warns before a restart that would start the same code (operator report 2026-09-25)', async () => {
    backend.tag = 'v1017';
    backend.checkout = 'v1017';
    await clickReload();
    const { message } = confirmAppMock.mock.calls[0][0] as { message: string };
    expect(message).toContain("Backend v1017's checkout is at v1017, so a restart loads v1017, not this desk's v1024.");
    expect(message).toContain('Pull master in that checkout first');
  });

  it('asks plainly when the checkout is ahead, or unknown', async () => {
    backend.tag = 'v1017';
    backend.checkout = 'v1024';
    await clickReload();
    expect((confirmAppMock.mock.calls[0][0] as { message: string }).message).not.toContain('Pull master');
  });

  it('says so when a reload came back still older than the desk, never just "reloaded"', async () => {
    backend.tag = 'v1017';
    backend.checkout = 'v1017';
    await clickReload();
    expect(container.textContent).toContain(
      'Backend reloaded · still v1017: its checkout is v1017 -- pull master, then reload',
    );
  });

  it('names the new revision when the restart loaded the pulled checkout', async () => {
    backend.tag = 'v1017';
    backend.checkout = 'v1024';
    backend.afterRestart = { tag: 'v1024', checkout: 'v1024' };
    await clickReload();
    expect(container.textContent).toContain('Backend reloaded · now v1024');
    expect(container.textContent).not.toContain('pull master');
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

  it('names the revision now answering once the reload lands', async () => {
    backend.tag = 'v1007';
    act(() => {
      root.render(<BackendReloadButton />);
    });
    await act(async () => {
      (container.querySelector('[data-testid="backend-reload-btn"]') as HTMLButtonElement).click();
      await Promise.resolve();
    });
    expect(container.textContent).toContain('Backend reloaded · now v1007');
    backend.tag = null;
  });

  it('shows why a reload did not happen, never "reloaded" (operator report 2026-09-24)', async () => {
    startLocalApiMock.mockResolvedValue({
      ok: false,
      mode: 'electron',
      error: 'Not restarted: backend v991 was started outside Nova, and its stop script was not found',
    });
    act(() => {
      root.render(<BackendReloadButton />);
    });
    await act(async () => {
      (container.querySelector('[data-testid="backend-reload-btn"]') as HTMLButtonElement).click();
      await Promise.resolve();
    });
    expect(container.textContent).toContain('Not restarted: backend v991');
    expect(container.textContent).not.toContain('Backend reloaded');
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
