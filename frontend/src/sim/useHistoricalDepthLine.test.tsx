/**
 * QA R44: the historical Level 2 holds the replay depth slot while shown, so a
 * bot is not refused "open its Level 2" with that panel open.
 *
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HistoricalDepth } from './HistoricalDepth';

const request = vi.hoisted(() => vi.fn());
vi.mock('./replayRequest', () => ({
  replayRequest: (...args: unknown[]) => request(...args),
  replayPost: (body: unknown) => ({ method: 'POST', body: JSON.stringify(body) }),
}));

const bodies = () => request.mock.calls.map((call) => JSON.parse((call[1] as { body: string }).body));

describe('HistoricalDepth holds the replay depth line (QA R44)', () => {
  let mount: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    request.mockReset();
    request.mockResolvedValue({ ok: true, held: true });
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
  });

  afterEach(() => {
    mount.remove();
  });

  it('holds the slot for the loaded symbol while mounted and lets go on unmount', () => {
    act(() => root.render(<HistoricalDepth depth={null} holdLineFor="grml" />));
    expect(request.mock.calls[0][0]).toBe('/history/depth-line');
    expect(bodies()).toEqual([{ symbol: 'GRML', hold: true }]);
    act(() => root.unmount());
    expect(bodies()).toEqual([{ symbol: 'GRML', hold: true }, { symbol: 'GRML', hold: false }]);
  });

  it('a capture gap panel (no symbol) asks for nothing', () => {
    act(() => root.render(<HistoricalDepth depth={null} />));
    act(() => root.unmount());
    expect(request).not.toHaveBeenCalled();
  });
});
