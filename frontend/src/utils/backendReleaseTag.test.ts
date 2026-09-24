/**
 * @vitest-environment jsdom
 */
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { formatScannerWindowTitle } from '../../electron/appTitle.mjs';
import { refreshBackendReleaseTag, resetBackendReleaseTagForTests } from './backendReleaseTag';
import { novaRendererReleaseTag } from './novaReleaseTag';
import { useNovaWindowTitle } from './useNovaWindowTitle';

function health(release_tag: unknown) {
  return vi.fn(async () => new Response(JSON.stringify({ status: 'ok', release_tag }), { status: 200 }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetBackendReleaseTagForTests();
});

describe('the backend revision in the window title', () => {
  it('names the revision the API answers with', async () => {
    const tag = novaRendererReleaseTag();
    const fetchMock = health(tag);
    vi.stubGlobal('fetch', fetchMock);
    renderHook(() => useNovaWindowTitle(false, null));
    await waitFor(() => expect(document.title).toBe(`${formatScannerWindowTitle(tag)} · backend ${tag}`));
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/\/api\/health$/);
  });

  it('says an older backend is older, so the operator knows to restart it', async () => {
    const tag = novaRendererReleaseTag();
    vi.stubGlobal('fetch', health('v1'));
    renderHook(() => useNovaWindowTitle(false, null));
    await waitFor(() => expect(document.title).toBe(`${formatScannerWindowTitle(tag)} · backend v1 (older -- restart it)`));
  });

  it('keeps the last answer while the API does not answer, and adds nothing before the first', async () => {
    const tag = novaRendererReleaseTag();
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('down'); }));
    renderHook(() => useNovaWindowTitle(false, null));
    await act(() => refreshBackendReleaseTag());
    expect(document.title).toBe(formatScannerWindowTitle(tag));
    vi.stubGlobal('fetch', health('v1'));
    await act(() => refreshBackendReleaseTag());
    await waitFor(() => expect(document.title).toContain('backend v1'));
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('restarting'); }));
    await act(() => refreshBackendReleaseTag());
    expect(document.title).toContain('backend v1');
  });

  it('an API older than the field says nothing rather than a guess', async () => {
    const tag = novaRendererReleaseTag();
    vi.stubGlobal('fetch', health(undefined));
    renderHook(() => useNovaWindowTitle(false, null));
    await waitFor(() => expect(document.title).toBe(formatScannerWindowTitle(tag)));
  });
});
