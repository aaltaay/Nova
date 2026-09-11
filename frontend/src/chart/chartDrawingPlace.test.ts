/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import {
  bindArmedToolPointer,
  placeArmedToolClick,
  pointerPointInElement,
} from './chartDrawingPlace';

const a = { time: 1, price: 10 };
const b = { time: 2, price: 12 };

describe('placeArmedToolClick', () => {
  it('ignores clicks when no tool is armed', () => {
    expect(placeArmedToolClick({
      tool: null,
      pending: null,
      anchor: a,
      twoAnchorTool: false,
      singleAnchorTool: false,
    })).toEqual({ action: 'ignore', pending: null });
  });

  it('collects two clicks for Trend Line, Extended Line, and Ray', () => {
    for (const tool of ['TrendLine', 'ExtendedLine', 'Ray']) {
      const first = placeArmedToolClick({
        tool,
        pending: null,
        anchor: a,
        twoAnchorTool: true,
        singleAnchorTool: false,
      });
      expect(first).toEqual({ action: 'wait', pending: a });
      const second = placeArmedToolClick({
        tool,
        pending: a,
        anchor: b,
        twoAnchorTool: true,
        singleAnchorTool: false,
      });
      expect(second).toEqual({ action: 'two', pending: null, anchors: [a, b] });
    }
  });

  it('completes Horizontal Line on the first click', () => {
    expect(placeArmedToolClick({
      tool: 'HorizontalLine',
      pending: null,
      anchor: a,
      twoAnchorTool: false,
      singleAnchorTool: true,
    })).toEqual({ action: 'one', pending: null, anchors: [a] });
  });
});

describe('pointerPointInElement', () => {
  it('maps client coordinates into the element box', () => {
    expect(pointerPointInElement(
      { getBoundingClientRect: () => ({ left: 40, top: 10 } as DOMRect) },
      55,
      30,
    )).toEqual({ x: 15, y: 20 });
  });
});

describe('bindArmedToolPointer', () => {
  it('fires one place point on primary pointerup while armed', () => {
    const el = document.createElement('div');
    Object.defineProperty(el, 'getBoundingClientRect', {
      value: () => ({ left: 0, top: 0, right: 100, bottom: 100, width: 100, height: 100 }),
    });
    const onPoint = vi.fn();
    const unbind = bindArmedToolPointer(el, () => true, onPoint);
    el.dispatchEvent(new PointerEvent('pointerdown', { button: 0, clientX: 8, clientY: 9, bubbles: true }));
    el.dispatchEvent(new PointerEvent('pointerup', { button: 0, clientX: 12, clientY: 16, bubbles: true }));
    expect(onPoint).toHaveBeenCalledTimes(1);
    expect(onPoint).toHaveBeenCalledWith({ x: 12, y: 16 });
    unbind();
  });

  it('does not place when the tool is not armed', () => {
    const el = document.createElement('div');
    const onPoint = vi.fn();
    const unbind = bindArmedToolPointer(el, () => false, onPoint);
    el.dispatchEvent(new PointerEvent('pointerup', { button: 0, clientX: 1, clientY: 1, bubbles: true }));
    expect(onPoint).not.toHaveBeenCalled();
    unbind();
  });
});
