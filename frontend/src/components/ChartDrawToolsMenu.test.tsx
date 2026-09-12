/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChartDrawToolsMenu, chartDrawToolsMenuPosition } from './ChartDrawToolsMenu';

function lineToolsMenu(): HTMLElement | null {
  return document.body.querySelector('[data-testid="chart-draw-tools-menu"]');
}

describe('ChartDrawToolsMenu', () => {
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
    lineToolsMenu()?.remove();
  });

  it('lists all six line tools with their hotkeys', async () => {
    await act(async () => {
      root.render(<ChartDrawToolsMenu activeTool={null} onToolClick={vi.fn()} />);
    });

    const toggle = container.querySelector<HTMLButtonElement>(
      'button[aria-label="Line drawing tools"]',
    );
    await act(async () => toggle?.click());

    const menu = lineToolsMenu();
    expect(menu).not.toBeNull();
    expect(menu?.textContent).toContain('Trendline');
    expect(menu?.textContent).toContain('Horizontal Line');
    expect(menu?.textContent).toContain('Vertical Line');
    expect(menu?.textContent).toContain('Extended');
    expect(menu?.textContent).toContain('Ray');
    expect(menu?.textContent).toContain('Horizontal Ray');
    for (const hotkey of ['Alt+T', 'Alt+H', 'Alt+V', 'Alt+E', 'Alt+J', 'Alt+R']) {
      expect(menu?.textContent).toContain(hotkey);
    }
  });

  it('portals the menu to document.body so toolbar overflow cannot clip it', async () => {
    const clip = document.createElement('div');
    clip.style.overflow = 'hidden';
    clip.style.height = '28px';
    document.body.appendChild(clip);
    clip.appendChild(container);

    await act(async () => {
      root.render(<ChartDrawToolsMenu activeTool={null} onToolClick={vi.fn()} />);
    });
    await act(async () => {
      container.querySelector<HTMLButtonElement>(
        'button[aria-label="Line drawing tools"]',
      )?.click();
    });

    const menu = lineToolsMenu();
    expect(menu).not.toBeNull();
    expect(menu?.parentElement).toBe(document.body);
    expect(clip.contains(menu)).toBe(false);
    clip.remove();
  });

  it('selects a tool and keeps it as the last-used main button', async () => {
    const onToolClick = vi.fn();
    await act(async () => {
      root.render(<ChartDrawToolsMenu activeTool={null} onToolClick={onToolClick} />);
    });

    await act(async () => {
      container.querySelector<HTMLButtonElement>(
        'button[aria-label="Line drawing tools"]',
      )?.click();
    });
    const horizontalRay = Array.from(lineToolsMenu()?.querySelectorAll('button') ?? []).find(
      (button) => button.textContent?.includes('Horizontal Ray'),
    );
    await act(async () => horizontalRay?.click());

    expect(onToolClick).toHaveBeenCalledWith('HorizontalRay');
    expect(
      container.querySelector<HTMLButtonElement>('button[aria-label="Use Horizontal Ray"]'),
    ).not.toBeNull();
    expect(lineToolsMenu()).toBeNull();
  });

  it('places the portaled menu just under the toolbar cluster', () => {
    expect(chartDrawToolsMenuPosition({ bottom: 80, left: 12 })).toEqual({
      top: 85,
      left: 12,
    });
  });
});
