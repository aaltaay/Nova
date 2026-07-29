/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useIbkrReconnectWarmup } from './useIbkrReconnectWarmup';

function Harness({ connected, onValue }: { connected: boolean; onValue: (v: boolean) => void }) {
  const warmingUp = useIbkrReconnectWarmup(connected);
  onValue(warmingUp);
  return null;
}

describe('useIbkrReconnectWarmup', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.useFakeTimers();
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.useRealTimers();
  });

  it('stays false when never connected', () => {
    let value = true;
    act(() => {
      root.render(<Harness connected={false} onValue={v => (value = v)} />);
    });
    expect(value).toBe(false);
  });

  it('turns true right after a false->true transition and clears after the warmup window', () => {
    let value = false;
    act(() => {
      root.render(<Harness connected={false} onValue={v => (value = v)} />);
    });
    expect(value).toBe(false);

    act(() => {
      root.render(<Harness connected={true} onValue={v => (value = v)} />);
    });
    expect(value).toBe(true);

    act(() => {
      vi.advanceTimersByTime(44_000);
    });
    expect(value).toBe(true);

    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(value).toBe(false);
  });

  it('clears immediately if disconnected again before the window elapses', () => {
    let value = false;
    act(() => {
      root.render(<Harness connected={false} onValue={v => (value = v)} />);
    });
    act(() => {
      root.render(<Harness connected={true} onValue={v => (value = v)} />);
    });
    expect(value).toBe(true);

    act(() => {
      root.render(<Harness connected={false} onValue={v => (value = v)} />);
    });
    expect(value).toBe(false);
  });
});
