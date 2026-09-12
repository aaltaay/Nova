/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import {
  bindHandleEditPointer,
  handlePointFromPointer,
  pointerHitsSelectedHandle,
} from './chartDrawingHandle';

describe('pointerHitsSelectedHandle', () => {
  it('is false when nothing is selected', () => {
    expect(
      pointerHitsSelectedHandle(
        { getSelectedDrawing: () => null, hitTestAnchor: () => 0 },
        { x: 10, y: 10 },
      ),
    ).toBe(false);
  });

  it('is false when the selected drawing has no handle under the point', () => {
    expect(
      pointerHitsSelectedHandle(
        { getSelectedDrawing: () => ({ id: 'tl-1' }), hitTestAnchor: () => null },
        { x: 10, y: 10 },
      ),
    ).toBe(false);
  });

  it('is true when the selected drawing reports a handle index', () => {
    expect(
      pointerHitsSelectedHandle(
        { getSelectedDrawing: () => ({ id: 'tl-1' }), hitTestAnchor: () => 1 },
        { x: 10, y: 10 },
      ),
    ).toBe(true);
  });
});

describe('handlePointFromPointer', () => {
  it('uses the container box so it matches the library hit test', () => {
    expect(
      handlePointFromPointer(
        { getBoundingClientRect: () => ({ left: 20, top: 8 } as DOMRect) },
        35,
        18,
      ),
    ).toEqual({ x: 15, y: 10 });
  });
});

describe('bindHandleEditPointer', () => {
  function host(): HTMLDivElement {
    const el = document.createElement('div');
    Object.defineProperty(el, 'getBoundingClientRect', {
      value: () => ({ left: 0, top: 0, right: 200, bottom: 100, width: 200, height: 100 }),
    });
    return el;
  }

  it('locks on handle pointerdown and unlocks on pointerup', () => {
    const el = host();
    const onEditingChange = vi.fn();
    const unbind = bindHandleEditPointer(
      el,
      () => ({ getSelectedDrawing: () => ({ id: 'tl-1' }), hitTestAnchor: () => 0 }),
      () => false,
      onEditingChange,
    );
    el.dispatchEvent(new PointerEvent('pointerdown', { button: 0, clientX: 12, clientY: 16, bubbles: true }));
    expect(onEditingChange).toHaveBeenCalledWith(true);
    el.dispatchEvent(new PointerEvent('pointerup', { button: 0, clientX: 40, clientY: 20, bubbles: true }));
    expect(onEditingChange).toHaveBeenCalledWith(false);
    unbind();
  });

  it('does not lock when the pointer misses the handle', () => {
    const el = host();
    const onEditingChange = vi.fn();
    const unbind = bindHandleEditPointer(
      el,
      () => ({ getSelectedDrawing: () => ({ id: 'tl-1' }), hitTestAnchor: () => null }),
      () => false,
      onEditingChange,
    );
    el.dispatchEvent(new PointerEvent('pointerdown', { button: 0, clientX: 12, clientY: 16, bubbles: true }));
    expect(onEditingChange).not.toHaveBeenCalled();
    unbind();
  });

  it('does not steal the D-010 place gesture while a tool is armed', () => {
    const el = host();
    const onEditingChange = vi.fn();
    const unbind = bindHandleEditPointer(
      el,
      () => ({ getSelectedDrawing: () => ({ id: 'tl-1' }), hitTestAnchor: () => 0 }),
      () => true,
      onEditingChange,
    );
    el.dispatchEvent(new PointerEvent('pointerdown', { button: 0, clientX: 12, clientY: 16, bubbles: true }));
    expect(onEditingChange).not.toHaveBeenCalled();
    unbind();
  });
});
