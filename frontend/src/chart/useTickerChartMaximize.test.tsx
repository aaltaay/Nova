/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { markChartFullscreen, takeEscapeConsumedForFullscreen } from './chartFullscreen';
import { useTickerChartMaximize } from './useTickerChartMaximize';

let current: Element | null = null;

function setFullscreenElement(el: Element | null) {
  current = el;
}

function installFullscreenMock() {
  setFullscreenElement(null);
  markChartFullscreen(false);
  takeEscapeConsumedForFullscreen();
  Object.defineProperty(document, 'fullscreenElement', {
    configurable: true,
    get: () => current,
  });
  HTMLElement.prototype.requestFullscreen = vi.fn(function (this: HTMLElement) {
    setFullscreenElement(this);
    document.dispatchEvent(new Event('fullscreenchange'));
    return Promise.resolve();
  });
  document.exitFullscreen = vi.fn(() => {
    setFullscreenElement(null);
    document.dispatchEvent(new Event('fullscreenchange'));
    return Promise.resolve();
  });
}

function Probe({
  maximizeInGrid,
  maximized,
  onMaximizeChange,
}: {
  maximizeInGrid?: boolean;
  maximized?: boolean;
  onMaximizeChange?: (next: boolean) => void;
}) {
  const api = useTickerChartMaximize({
    maximizeInGrid,
    maximized,
    onMaximizeChange,
  });
  return (
    <div>
      <div ref={api.slotRef} data-testid="slot" />
      <button type="button" data-testid="toggle" onClick={api.toggleMaximize} />
      <span data-testid="portal">{api.portalMaximized ? '1' : '0'}</span>
      <span data-testid="header">{api.headerMaximized ? '1' : '0'}</span>
      <span data-testid="fs">{api.isFullscreen ? '1' : '0'}</span>
    </div>
  );
}

describe('useTickerChartMaximize', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    installFullscreenMock();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    current = null;
    markChartFullscreen(false);
    vi.restoreAllMocks();
  });

  it('grid header toggle requests fullscreen and does not call onMaximizeChange', async () => {
    const onMaximizeChange = vi.fn();
    await act(async () => {
      root.render(
        <Probe maximizeInGrid maximized={false} onMaximizeChange={onMaximizeChange} />,
      );
    });
    await act(async () => {
      (container.querySelector('[data-testid="toggle"]') as HTMLButtonElement).click();
    });
    expect(onMaximizeChange).not.toHaveBeenCalled();
    expect(HTMLElement.prototype.requestFullscreen).toHaveBeenCalled();
    expect(container.querySelector('[data-testid="portal"]')?.textContent).toBe('0');
    expect(container.querySelector('[data-testid="fs"]')?.textContent).toBe('1');
    expect(container.querySelector('[data-testid="header"]')?.textContent).toBe('1');
    expect(document.fullscreenElement).toBeTruthy();
  });

  it('non-grid header toggle still uses the desk portal, not requestFullscreen', async () => {
    await act(async () => {
      root.render(<Probe />);
    });
    const callsBefore = vi.mocked(HTMLElement.prototype.requestFullscreen).mock.calls.length;
    await act(async () => {
      (container.querySelector('[data-testid="toggle"]') as HTMLButtonElement).click();
    });
    expect(container.querySelector('[data-testid="portal"]')?.textContent).toBe('1');
    expect(vi.mocked(HTMLElement.prototype.requestFullscreen).mock.calls.length).toBe(
      callsBefore,
    );
  });
});
