/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import {
  bindPlacePreviewPointer,
  CHART_PLACE_PREVIEW_ID,
  createPlacePreviewDrawing,
  detachPlacePreview,
  markPlacePreviewHost,
  movePlacePreview,
  shouldShowPlacePreview,
} from './chartDrawingPreview';

const a = { time: 1 as const, price: 10 };
const b = { time: 2 as const, price: 12 };

describe('shouldShowPlacePreview', () => {
  it('is false until a two-click tool has point A', () => {
    expect(shouldShowPlacePreview(null, null)).toBe(false);
    expect(shouldShowPlacePreview('TrendLine', null)).toBe(false);
    expect(shouldShowPlacePreview('HorizontalLine', a)).toBe(false);
  });

  it.each(['TrendLine', 'ExtendedLine', 'Ray'])(
    'is true for %s after point A',
    (tool) => {
      expect(shouldShowPlacePreview(tool, a)).toBe(true);
    },
  );
});

describe('createPlacePreviewDrawing', () => {
  it.each(['TrendLine', 'ExtendedLine', 'Ray'])(
    'builds a %s primitive with A then cursor, not via addDrawing',
    (tool) => {
      const drawing = createPlacePreviewDrawing(tool, a, b);
      expect(drawing).toBeTruthy();
      expect(drawing?.id).toBe(CHART_PLACE_PREVIEW_ID);
      expect(drawing?.anchors).toEqual([a, b]);
      expect(drawing?.isAttached()).toBe(false);
    },
  );

  it('returns null for a one-click tool', () => {
    expect(createPlacePreviewDrawing('HorizontalLine', a, b)).toBeNull();
  });
});

describe('movePlacePreview', () => {
  it('updates only the second anchor', () => {
    const drawing = createPlacePreviewDrawing('TrendLine', a, a);
    expect(drawing).toBeTruthy();
    if (!drawing) return;
    movePlacePreview(drawing, b);
    expect(drawing.anchors[0]).toEqual(a);
    expect(drawing.anchors[1]).toEqual(b);
  });
});

describe('markPlacePreviewHost', () => {
  it('stamps preview and pending flags', () => {
    const host = document.createElement('div');
    markPlacePreviewHost(host, true);
    expect(host.dataset.drawingPreview).toBe('1');
    expect(host.dataset.placePending).toBe('1');
    markPlacePreviewHost(host, false);
    expect(host.dataset.drawingPreview).toBe('');
    expect(host.dataset.placePending).toBe('');
  });
});

describe('detachPlacePreview', () => {
  it('is a no-op for null', () => {
    expect(() => detachPlacePreview(null)).not.toThrow();
  });
});

describe('bindPlacePreviewPointer', () => {
  it('follows the pointer only while previewing', () => {
    const el = document.createElement('div');
    Object.defineProperty(el, 'getBoundingClientRect', {
      value: () => ({ left: 0, top: 0, right: 200, bottom: 100, width: 200, height: 100 }),
    });
    const onPoint = vi.fn();
    let previewing = false;
    const unbind = bindPlacePreviewPointer(el, () => previewing, onPoint);
    el.dispatchEvent(new PointerEvent('pointermove', { clientX: 40, clientY: 20, bubbles: true }));
    expect(onPoint).not.toHaveBeenCalled();
    previewing = true;
    el.dispatchEvent(new PointerEvent('pointermove', { clientX: 40, clientY: 20, bubbles: true }));
    expect(onPoint).toHaveBeenCalledWith({ x: 40, y: 20 });
    unbind();
  });
});
