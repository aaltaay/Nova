/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import { isElectronRenderer, nudgeElectronPaint } from './nudgeElectronPaint';

describe('isElectronRenderer', () => {
  it('detects Electron and ignores Chrome/Vite', () => {
    expect(isElectronRenderer('Mozilla/5.0 Electron/37.2.0')).toBe(true);
    expect(isElectronRenderer('Mozilla/5.0 Chrome/138.0.0.0')).toBe(false);
  });
});

describe('nudgeElectronPaint', () => {
  it('applies a translateZ tick then clears it on rAF', () => {
    const raf = vi
      .spyOn(globalThis, 'requestAnimationFrame')
      .mockImplementation((cb: FrameRequestCallback) => {
        cb(0);
        return 1;
      });
    nudgeElectronPaint(document);
    expect(document.documentElement.style.transform).toBe('');
    raf.mockRestore();
  });
});
