/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CHART_LINE_TOOLS } from '../chart/chartDrawingConfig';
import { ChartDrawTools } from './ChartDrawTools';

describe('ChartDrawTools', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('shows all six line tools as buttons with their hotkeys, and no dropdown', async () => {
    await act(async () => {
      root.render(<ChartDrawTools activeTool={null} onToolClick={vi.fn()} />);
    });

    expect(container.querySelector('[data-testid="chart-draw-tools"]')).not.toBeNull();
    expect(container.querySelector('[aria-haspopup="menu"]')).toBeNull();
    expect(document.body.querySelector('[role="menu"]')).toBeNull();
    const buttons = container.querySelectorAll('button');
    expect(buttons).toHaveLength(CHART_LINE_TOOLS.length);
    expect(CHART_LINE_TOOLS).toHaveLength(6);
    for (const tool of CHART_LINE_TOOLS) {
      const button = container.querySelector<HTMLButtonElement>(`[aria-label="Use ${tool.label}"]`);
      expect(button).not.toBeNull();
      expect(button?.title).toBe(`${tool.label} (${tool.hotkey})`);
    }
  });

  it('arms the pressed tool in one click', async () => {
    const onToolClick = vi.fn();
    await act(async () => {
      root.render(<ChartDrawTools activeTool={null} onToolClick={onToolClick} />);
    });
    await act(async () => {
      container.querySelector<HTMLButtonElement>('[aria-label="Use Horizontal Ray"]')?.click();
    });
    expect(onToolClick).toHaveBeenCalledWith('HorizontalRay');
  });

  it('marks only the active tool pressed', async () => {
    await act(async () => {
      root.render(<ChartDrawTools activeTool="Ray" onToolClick={vi.fn()} />);
    });
    const pressed = [...container.querySelectorAll('button[aria-pressed="true"]')];
    expect(pressed.map((b) => b.getAttribute('aria-label'))).toEqual(['Use Ray']);
    expect(pressed[0].classList.contains('chart-tool-btn--active')).toBe(true);
  });
});
