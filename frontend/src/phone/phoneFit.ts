/**
 * No phone screen scrolls. The screens were drawn for 360 x 720 upright (740 x 320 on its side) and
 * stretch to fill anything larger. On anything smaller -- a browser tab with its address bar showing
 * -- the whole page is shrunk by one factor until the drawn size fits, instead of cutting a row off.
 */
import { useEffect, useState } from 'react';

export interface DesignSize {
  width: number;
  height: number;
}

export const PORTRAIT: DesignSize = { width: 360, height: 720 };
export const LANDSCAPE: DesignSize = { width: 740, height: 320 };

export interface Fit {
  /** 1 when the viewport is at least the drawn size; under 1 shrinks the page. */
  zoom: number;
  /** The page's size in its own pixels: the viewport divided by the zoom. */
  width: number;
  height: number;
}

export function fitFor(viewport: DesignSize, design: DesignSize): Fit {
  const zoom = Math.min(1, viewport.width / design.width, viewport.height / design.height);
  const safe = zoom > 0 && Number.isFinite(zoom) ? zoom : 1;
  return { zoom: safe, width: viewport.width / safe, height: viewport.height / safe };
}

function viewport(): DesignSize {
  const vv = window.visualViewport;
  return { width: vv?.width ?? window.innerWidth, height: vv?.height ?? window.innerHeight };
}

/** The viewport, kept current as the phone turns or its browser bars come and go. */
export function useViewport(): DesignSize {
  const [size, setSize] = useState<DesignSize>(viewport);
  useEffect(() => {
    const read = () => setSize(viewport());
    window.addEventListener('resize', read);
    window.visualViewport?.addEventListener('resize', read);
    return () => {
      window.removeEventListener('resize', read);
      window.visualViewport?.removeEventListener('resize', read);
    };
  }, []);
  return size;
}
