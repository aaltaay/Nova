/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChartDrawToolsMenu } from './ChartDrawToolsMenu';

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
  });

  it('lists all six line tools with their hotkeys', async () => {
    await act(async () => {
      root.render(<ChartDrawToolsMenu activeTool={null} onToolClick={vi.fn()} />);
    });

    const toggle = container.querySelector<HTMLButtonElement>(
      'button[aria-label="Line drawing tools"]',
    );
    await act(async () => toggle?.click());

    expect(container.textContent).toContain('Trendline');
    expect(container.textContent).toContain('Horizontal Line');
    expect(container.textContent).toContain('Vertical Line');
    expect(container.textContent).toContain('Extended');
    expect(container.textContent).toContain('Ray');
    expect(container.textContent).toContain('Horizontal Ray');
    for (const hotkey of ['Alt+T', 'Alt+H', 'Alt+V', 'Alt+E', 'Alt+J', 'Alt+R']) {
      expect(container.textContent).toContain(hotkey);
    }
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
    const horizontalRay = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent?.includes('Horizontal Ray'),
    );
    await act(async () => horizontalRay?.click());

    expect(onToolClick).toHaveBeenCalledWith('HorizontalRay');
    expect(
      container.querySelector<HTMLButtonElement>('button[aria-label="Use Horizontal Ray"]'),
    ).not.toBeNull();
    expect(container.querySelector('[role="menu"]')).toBeNull();
  });
});
