/**
 * Tiles slide to their new place when the ranks change (approved mockup: "Tiles slide to their new
 * place (½ s)"). FLIP: remember each tile's box, and after a reorder start it where it was and let
 * the transform run back to zero.
 */
import { useCallback, useLayoutEffect, useRef } from 'react';

const SLIDE_MS = 500;

export function useTileSlide(order: string): (symbol: string) => (el: HTMLDivElement | null) => void {
  const nodes = useRef(new Map<string, HTMLDivElement>());
  const boxes = useRef(new Map<string, DOMRect>());

  const refs = useRef(new Map<string, (el: HTMLDivElement | null) => void>());

  // One stable ref callback per symbol, so a re-render does not detach and re-attach every tile.
  const refFor = useCallback((symbol: string) => {
    let ref = refs.current.get(symbol);
    if (!ref) {
      ref = (el: HTMLDivElement | null) => {
        if (el) nodes.current.set(symbol, el);
        else {
          nodes.current.delete(symbol);
          refs.current.delete(symbol);
        }
      };
      refs.current.set(symbol, ref);
    }
    return ref;
  }, []);

  useLayoutEffect(() => {
    const reduce = typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const next = new Map<string, DOMRect>();
    nodes.current.forEach((el, symbol) => {
      const box = el.getBoundingClientRect();
      next.set(symbol, box);
      const was = boxes.current.get(symbol);
      if (!was || reduce || typeof el.animate !== 'function') return;
      const dx = was.left - box.left;
      const dy = was.top - box.top;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
      el.animate(
        [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'translate(0, 0)' }],
        { duration: SLIDE_MS, easing: 'cubic-bezier(.2,.8,.2,1)' },
      );
    });
    boxes.current = next;
  }, [order]);

  // A resized window moves every tile: start the next slide from where they are now.
  useLayoutEffect(() => {
    const remeasure = () => {
      const next = new Map<string, DOMRect>();
      nodes.current.forEach((el, symbol) => next.set(symbol, el.getBoundingClientRect()));
      boxes.current = next;
    };
    window.addEventListener('resize', remeasure);
    return () => window.removeEventListener('resize', remeasure);
  }, []);

  return refFor;
}
