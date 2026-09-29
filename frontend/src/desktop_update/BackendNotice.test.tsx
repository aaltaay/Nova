/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { EngineSync } from './updateView';

const tags = vi.hoisted(() => ({ backend: 'v1025' as string | null, checkout: 'v1027' as string | null }));
const startLocalApi = vi.hoisted(() => vi.fn(async () => ({ ok: true, mode: 'electron' })));
const confirmApp = vi.hoisted(() => vi.fn(async () => true));

vi.mock('../utils/backendReleaseTag', () => ({
  useBackendReleaseTag: () => tags.backend,
  useBackendCheckoutTag: () => tags.checkout,
  refreshBackendReleaseTag: vi.fn(async () => undefined),
}));
vi.mock('../utils/novaReleaseTag', () => ({ novaRendererReleaseTag: () => 'v1029' }));
vi.mock('../utils/startLocalApi', () => ({ startLocalApi }));
vi.mock('../ux', () => ({ confirmApp }));

import { BackendNotice } from './BackendNotice';

const engine: EngineSync = { owner: 'C:\\Nova', attachedToOwner: true, running: null, last: null };

function answerCheck(body: unknown) {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => body })));
}

beforeEach(() => {
  tags.backend = 'v1025';
  tags.checkout = 'v1027';
  startLocalApi.mockClear();
  confirmApp.mockClear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('BackendNotice', () => {
  it('restarts in one click when the backend says nothing is open', async () => {
    answerCheck({ schema_version: 1, safe: true, open: [], unknown: [] });
    render(<BackendNotice engine={engine} act={vi.fn()} />);
    expect(screen.getByTestId('backend-notice').textContent).toContain('Its checkout holds v1027');
    fireEvent.click(screen.getByRole('button', { name: 'Restart backend now' }));
    await waitFor(() => expect(startLocalApi).toHaveBeenCalledTimes(1));
    expect(confirmApp).not.toHaveBeenCalled();
  });

  it('lists what is open and restarts only once confirmed', async () => {
    answerCheck({
      schema_version: 1, safe: false, unknown: [],
      open: [{ kind: 'recording', text: "Recording MSGY: a few seconds' gap, then it resumes on its own" }],
    });
    confirmApp.mockResolvedValueOnce(false);
    render(<BackendNotice engine={engine} act={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Restart backend now' }));
    await waitFor(() => expect(confirmApp).toHaveBeenCalledTimes(1));
    expect((confirmApp.mock.calls[0] as unknown as [{ message: string }])[0].message).toContain('- Recording MSGY');
    expect(startLocalApi).not.toHaveBeenCalled();
  });

  it('asks the main process to pull when the checkout holds nothing newer', async () => {
    tags.checkout = 'v1025';
    answerCheck({ schema_version: 1, safe: true, open: [], unknown: [] });
    const act = vi.fn();
    render(<BackendNotice engine={engine} act={act} />);
    fireEvent.click(screen.getByRole('button', { name: 'Pull master and restart' }));
    await waitFor(() => expect(act).toHaveBeenCalledWith('backend-sync'));
    expect(confirmApp).toHaveBeenCalledTimes(1);
    expect(startLocalApi).not.toHaveBeenCalled();
  });

  it('shows nothing for a current backend, and hides on Later', () => {
    tags.backend = 'v1029';
    tags.checkout = 'v1029';
    const { rerender } = render(<BackendNotice engine={engine} act={vi.fn()} />);
    expect(screen.queryByTestId('backend-notice')).toBeNull();
    tags.backend = 'v1025';
    tags.checkout = 'v1027';
    rerender(<BackendNotice engine={{ ...engine }} act={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Later' }));
    expect(screen.queryByTestId('backend-notice')).toBeNull();
  });
});
