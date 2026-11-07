/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { L2_SIZE_STORAGE_KEY } from '../constants';
import { Level2Frame } from './Level2Frame';
import { Level2SpreadRow, spreadPercent } from './Level2SpreadRow';
import { reloadLevel2SizeForTesting } from './level2Size';

afterEach(cleanup);

function mount(bid: number | null = 0.7824, ask: number | null = 0.7854) {
  return render(
    <Level2Frame data-testid="frame">
      <Level2SpreadRow bid={bid} ask={ask} />
      <div className="das-l2-montage" />
    </Level2Frame>,
  );
}

describe('the spread row over the book', () => {
  it('shows the best bid, the spread with its share of the ask, and the best ask', () => {
    const { getByTestId } = mount();
    expect(getByTestId('l2-spread-bid').textContent).toBe('0.7824');
    expect(getByTestId('l2-spread-value').textContent).toBe('0.003');
    expect(getByTestId('l2-spread-pct').textContent).toBe('0.38%');
    expect(getByTestId('l2-spread-ask').textContent).toBe('0.7854');
  });

  it('sits over the book, before the montage', () => {
    const { getByTestId } = mount();
    const frame = getByTestId('frame');
    expect(frame.firstElementChild?.getAttribute('data-testid')).toBe('l2-spread');
    expect(frame.lastElementChild?.className).toBe('das-l2-montage');
  });

  it('draws nothing without both sides', () => {
    const { queryByTestId } = mount(0.7824, null);
    expect(queryByTestId('l2-spread')).toBeNull();
    expect(spreadPercent(1, 0)).toBeNull();
  });
});

describe("the Level 2 pane's right-click size menu", () => {
  beforeEach(() => {
    localStorage.clear();
    reloadLevel2SizeForTesting();
  });

  it('carries the size on the pane, large by default', () => {
    const { getByTestId } = mount();
    expect(getByTestId('frame').getAttribute('data-l2-size')).toBe('large');
  });

  it('opens on a right click with the current size ticked, and a pick changes the pane and keeps it', () => {
    const { getByTestId, queryByTestId } = mount();
    expect(queryByTestId('l2-size-menu')).toBeNull();
    fireEvent.contextMenu(getByTestId('frame'), { clientX: 40, clientY: 50 });
    const menu = getByTestId('l2-size-menu');
    expect(menu.getAttribute('role')).toBe('menu');
    expect(menu.querySelectorAll('[role="menuitemradio"]')).toHaveLength(3);
    expect(getByTestId('l2-size-large').getAttribute('aria-checked')).toBe('true');
    expect(getByTestId('l2-size-small').getAttribute('aria-checked')).toBe('false');

    fireEvent.click(getByTestId('l2-size-medium'));
    expect(queryByTestId('l2-size-menu')).toBeNull();
    expect(getByTestId('frame').getAttribute('data-l2-size')).toBe('medium');
    expect(JSON.parse(localStorage.getItem(L2_SIZE_STORAGE_KEY) ?? 'null'))
      .toEqual({ schema_version: 1, value: 'medium' });
  });

  it('closes on Escape and on a click outside, changing nothing', () => {
    const { getByTestId, queryByTestId } = mount();
    fireEvent.contextMenu(getByTestId('frame'), { clientX: 40, clientY: 50 });
    expect(queryByTestId('l2-size-menu')).not.toBeNull();
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(queryByTestId('l2-size-menu')).toBeNull();

    fireEvent.contextMenu(getByTestId('frame'), { clientX: 40, clientY: 50 });
    act(() => {
      document.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    });
    expect(queryByTestId('l2-size-menu')).toBeNull();
    expect(getByTestId('frame').getAttribute('data-l2-size')).toBe('large');
    expect(localStorage.getItem(L2_SIZE_STORAGE_KEY)).toBeNull();
  });
});
