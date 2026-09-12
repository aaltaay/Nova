/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TickerChartControls } from './TickerChartControls';

const noop = vi.fn();

function renderControls(fillingHint: string | null) {
  return (
    <TickerChartControls
      activeTool={null}
      enabledIndicators={['vwap']}
      lockTimeframe={false}
      maximized={false}
      timeframe="1Min"
      fillingHint={fillingHint}
      onClearAll={noop}
      onIndicatorToggle={noop}
      onMaximize={noop}
      onTimeframeChange={noop}
      onToolClick={noop}
    />
  );
}

describe('TickerChartControls filling hint', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('puts the filling status in the header, not on the plot', async () => {
    await act(async () => {
      root.render(renderControls('as of 15:48 ET, filling…'));
    });
    const hint = container.querySelector('.chart-filling-hint');
    expect(hint?.textContent).toBe('as of 15:48 ET, filling…');
    expect(container.querySelector('.chart-header')?.contains(hint)).toBe(true);
    expect(container.querySelector('.chart-body')).toBeNull();
  });

  it('hides the filling chip when the store is settled', async () => {
    await act(async () => {
      root.render(renderControls(null));
    });
    expect(container.querySelector('.chart-filling-hint')).toBeNull();
  });

  it('compact grid pane: one header line, no toolbar, maximize stays reachable', async () => {
    await act(async () => {
      root.render(
        <TickerChartControls
          activeTool={null}
          enabledIndicators={['vwap']}
          lockTimeframe
          maximized={false}
          timeframe="5Min"
          title="5-Minute"
          usingMock={false}
          compact
          onClearAll={noop}
          onIndicatorToggle={noop}
          onMaximize={noop}
          onTimeframeChange={noop}
          onToolClick={noop}
        />,
      );
    });
    expect(container.querySelector('.chart-header--compact')).toBeTruthy();
    expect(container.querySelector('.chart-toolbar')).toBeNull();
    expect(container.querySelector('[aria-label="Indicators"]')).toBeNull();
    expect(container.querySelector('.chart-header [aria-label="Maximize chart"]')).toBeTruthy();
  });

  it('grid-local maximize keeps compact chrome because the desk toolbar stays', async () => {
    await act(async () => {
      root.render(
        <TickerChartControls
          activeTool={null}
          enabledIndicators={['vwap']}
          lockTimeframe
          maximized
          timeframe="5Min"
          title="5-Minute"
          usingMock={false}
          compact
          keepCompactWhenMaximized
          onClearAll={noop}
          onIndicatorToggle={noop}
          onMaximize={noop}
          onTimeframeChange={noop}
          onToolClick={noop}
        />,
      );
    });
    expect(container.querySelector('.chart-toolbar')).toBeNull();
    expect(container.querySelector('[aria-label="Indicators"]')).toBeNull();
    expect(container.querySelector('.chart-header [aria-label="Restore chart"]')).toBeTruthy();
  });

  it('compact pane that is maximized gets its own toolbar back', async () => {
    await act(async () => {
      root.render(
        <TickerChartControls
          activeTool={null}
          enabledIndicators={['vwap']}
          lockTimeframe
          maximized
          timeframe="5Min"
          usingMock={false}
          compact
          onClearAll={noop}
          onIndicatorToggle={noop}
          onMaximize={noop}
          onTimeframeChange={noop}
          onToolClick={noop}
        />,
      );
    });
    expect(container.querySelector('.chart-toolbar')).toBeTruthy();
    expect(container.querySelector('[aria-label="Indicators"]')).toBeTruthy();
    expect(container.querySelector('[aria-label="Restore chart"]')).toBeTruthy();
  });

  it('does not spend chart header space on a session legend', async () => {
    await act(async () => {
      root.render(renderControls(null));
    });
    expect(container.querySelector('.chart-session-legend')).toBeNull();
    expect(container.textContent).not.toContain('Premarket');
    expect(container.textContent).not.toContain('RTH');
    expect(container.textContent).not.toContain('After-hours');
  });
});
