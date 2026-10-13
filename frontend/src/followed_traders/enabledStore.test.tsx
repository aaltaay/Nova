/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { resetFollowedGateForTests, useFollowedTradersEnabled } from './enabledStore';

function Probe() {
  return <span data-testid="gate">{useFollowedTradersEnabled() ? 'on' : 'off'}</span>;
}

describe('followed traders gate', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    resetFollowedGateForTests();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
    vi.useRealTimers();
    resetFollowedGateForTests();
  });

  async function mount() {
    await act(async () => {
      root.render(<Probe />);
    });
    await act(async () => {
      await Promise.resolve();
    });
  }
  const shown = () => container.querySelector('[data-testid="gate"]')!.textContent;

  it('stays off when the route does not exist (no feed configured), and asks once', async () => {
    const fetchMock = vi.fn(async () => new Response('', { status: 404 }));
    vi.stubGlobal('fetch', fetchMock);
    await mount();
    expect(shown()).toBe('off');
    await act(async () => {
      root.render(<><Probe /><Probe /></>);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toMatch(/\/api\/followed-traders\/config$/);
  });

  it('turns on when the backend says the feed is configured', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ schema_version: 1, enabled: true }))));
    await mount();
    expect(shown()).toBe('on');
  });

  it('asks again when the backend did not answer at all', async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(new Response(JSON.stringify({ schema_version: 1, enabled: true })));
    vi.stubGlobal('fetch', fetchMock);
    await mount();
    expect(shown()).toBe('off');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(shown()).toBe('on');
  });
});
