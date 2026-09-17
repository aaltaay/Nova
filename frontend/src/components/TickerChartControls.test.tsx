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

  it('grid-local maximize keeps compact chrome and the expand icon for fullscreen', async () => {
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
          keepCompactWhenMaximized
          useFullscreenExpand
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
    expect(container.querySelector('.chart-header [aria-label="Enter full screen"]')).toBeTruthy();
    expect(container.querySelector('.chart-header [aria-label="Restore chart"]')).toBeNull();
  });

  it('fullscreen expand shows Exit full screen and grows pane chrome', async () => {
    await act(async () => {
      root.render(
        <TickerChartControls
          activeTool={null}
          enabledIndicators={['vwap']}
          lockTimeframe
          maximized
          timeframe="10Sec"
          title="10-Second"
          usingMock={false}
          compact
          useFullscreenExpand
          onClearAll={noop}
          onIndicatorToggle={noop}
          onMaximize={noop}
          onTimeframeChange={noop}
          onToolClick={noop}
        />,
      );
    });
    expect(container.querySelector('.chart-toolbar')).toBeTruthy();
    expect(container.querySelector('[aria-label="Exit full screen"]')).toBeTruthy();
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

  it('maximized toolbar spreads line tools and keeps timeframe plus indicators', async () => {
    const onToolClick = vi.fn();
    const onIndicatorToggle = vi.fn();
    const onTimeframeChange = vi.fn();
    await act(async () => {
      root.render(
        <TickerChartControls
          activeTool={null}
          enabledIndicators={['emas', 'vwap']}
          lockTimeframe={false}
          maximized
          timeframe="5Min"
          usingMock={false}
          onClearAll={noop}
          onIndicatorToggle={onIndicatorToggle}
          onMaximize={noop}
          onTimeframeChange={onTimeframeChange}
          onToolClick={onToolClick}
        />,
      );
    });

    expect(container.querySelector('[data-testid="chart-draw-tools-flat"]')).toBeTruthy();
    expect(container.querySelector('button[aria-haspopup="menu"]')).toBeNull();
    expect(container.querySelector('[aria-label="Use Trendline"]')).toBeTruthy();
    expect(container.querySelector('[aria-label="Use Horizontal Ray"]')).toBeTruthy();
    expect(container.querySelector('[aria-label="Timeframe"]')).toBeTruthy();
    expect(container.querySelector('[aria-label="Indicators"]')).toBeTruthy();
    expect(container.textContent).toContain('EMAs');
    expect(container.textContent).toContain('VWAP');
    expect(container.textContent).toContain('RSI');
    expect(container.textContent).toContain('MACD');

    await act(async () => {
      container.querySelector<HTMLButtonElement>('[aria-label="Use Ray"]')?.click();
    });
    expect(onToolClick).toHaveBeenCalledWith('Ray');

    const rsi = [...container.querySelectorAll<HTMLButtonElement>('.chart-tab')].find(
      (button) => button.textContent === 'RSI',
    );
    await act(async () => rsi?.click());
    expect(onIndicatorToggle).toHaveBeenCalledWith('rsi');

    const oneMin = [...container.querySelectorAll<HTMLButtonElement>('.chart-tab')].find(
      (button) => button.textContent === '1m',
    );
    expect(oneMin).toBeTruthy();
    await act(async () => oneMin?.click());
    expect(onTimeframeChange).toHaveBeenCalledWith('1Min');
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
