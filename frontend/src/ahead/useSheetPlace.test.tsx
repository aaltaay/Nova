/**
 * @vitest-environment jsdom
 *
 * The Ahead panel's place on the page (ADR 065): docked, its holder gives the charts the panel's width less room and
 * gets it back on close; over the other panes, it starts below the chart grid's toolbar.
 */
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import { publishKeepClear, resetKeepClearForTesting, SHEET_MAX_PX } from './aheadSheetPlace';
import { belowWindow, DOCK_CLASS, DOCK_WIDTH_VAR, useSheetPlace } from './useSheetPlace';

const SYM = 'XYZ';

function rect(left: number, right: number, top: number, bottom: number): DOMRect {
  return { left, right, top, bottom, x: left, y: top, width: right - left, height: bottom - top } as DOMRect;
}

function Probe() {
  const { ref, place } = useSheetPlace(SYM, true);
  return <aside ref={ref} data-testid="probe" data-dock={String(place?.dock)} data-side={place?.side}
    data-top={place?.top} data-bottom={place?.bottom} />;
}

function mount(holderBottom = 1000) {
  const holder = document.createElement('div');
  holder.getBoundingClientRect = () => rect(0, 1920, 0, holderBottom);
  const bar = document.createElement('div');
  bar.className = 'chart-desk-toolbar';
  bar.getBoundingClientRect = () => rect(0, 1920, 0, 34);
  holder.appendChild(bar);
  document.body.appendChild(holder);
  const view = render(<Probe />, { container: holder.appendChild(document.createElement('div')) });
  return { holder, view };
}

beforeAll(() => {
  // jsdom lays nothing out: the panel's positioned parent is the element holding it.
  Object.defineProperty(HTMLElement.prototype, 'offsetParent', {
    configurable: true,
    get(this: HTMLElement) {
      return this.parentElement?.parentElement ?? null;
    },
  });
});

afterEach(() => {
  cleanup();
  act(() => resetKeepClearForTesting());
  document.body.innerHTML = '';
});

describe('useSheetPlace', () => {
  it('docks beside the charts when the 1-minute pane fills the grid, and hands the room back on close', () => {
    act(() => publishKeepClear(SYM, { left: 1240, right: 1920, paneLeft: 0, paneRight: 1920 }));
    const { holder, view } = mount();
    const probe = view.getByTestId('probe');
    expect(probe.dataset.dock).toBe('true');
    expect(probe.dataset.side).toBe('left');
    expect(probe.dataset.top).toBe('0');
    expect(holder.classList.contains(DOCK_CLASS.left)).toBe(true);
    expect(holder.style.getPropertyValue(DOCK_WIDTH_VAR)).toBe(`${SHEET_MAX_PX}px`);
    view.unmount();
    expect(holder.classList.contains(DOCK_CLASS.left)).toBe(false);
    expect(holder.style.getPropertyValue(DOCK_WIDTH_VAR)).toBe('');
  });

  it('slides over the other panes below the toolbar when there is room beside the 1-minute pane', () => {
    act(() => publishKeepClear(SYM, { left: 1700, right: 1920, paneLeft: 960, paneRight: 1920 }));
    const { holder, view } = mount();
    const probe = view.getByTestId('probe');
    expect(probe.dataset.dock).toBe('false');
    expect(probe.dataset.side).toBe('left');
    expect(probe.dataset.top).toBe('34');
    expect(holder.classList.contains(DOCK_CLASS.left)).toBe(false);
  });

  it('ends at the window bottom when its holder runs past it, so the body scrolls to the last card', () => {
    expect(belowWindow(1000, 768)).toBe(232);
    expect(belowWindow(700, 768)).toBe(0);
    act(() => publishKeepClear(SYM, { left: 1700, right: 1920, paneLeft: 960, paneRight: 1920 }));
    const inside = mount(Math.min(700, window.innerHeight));
    expect(inside.view.getByTestId('probe').dataset.bottom).toBe('0');
    inside.view.unmount();
    const past = mount(window.innerHeight + 300);
    expect(past.view.getByTestId('probe').dataset.bottom).toBe('300');
  });
});
