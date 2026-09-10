/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { IBKR_CLIENT_PORTAL_URL } from '../constants';
import { openIbkrClientPortal } from './openIbkrClientPortal';

describe('openIbkrClientPortal', () => {
  afterEach(() => {
    delete window.novaDesktop;
    vi.restoreAllMocks();
  });

  it('uses the desktop external-browser bridge in Electron', async () => {
    const openExternal = vi.fn().mockResolvedValue(true);
    window.novaDesktop = {
      isDesktop: true,
      apiBase: 'http://127.0.0.1:8000',
      getVersion: vi.fn(),
      openExternal,
    };

    await openIbkrClientPortal();

    expect(openExternal).toHaveBeenCalledWith(IBKR_CLIENT_PORTAL_URL);
  });

  it('opens the official portal in a browser tab outside Electron', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);

    await openIbkrClientPortal();

    expect(open).toHaveBeenCalledWith(
      IBKR_CLIENT_PORTAL_URL,
      '_blank',
      'noopener,noreferrer',
    );
  });
});
