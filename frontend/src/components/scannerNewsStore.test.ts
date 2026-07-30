/** @vitest-environment jsdom */
import { createElement, useEffect } from 'react';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  resetScannerNewsForTests,
  setScannerNews,
  useScannerNews,
} from './scannerNewsStore';

function Probe({
  expected,
  onMap,
}: {
  expected: 'live' | 'sample';
  onMap: (size: number, hasSym: boolean) => void;
}) {
  const map = useScannerNews(expected);
  useEffect(() => {
    onMap(map.size, map.has('SMTI'));
  }, [map, onMap]);
  return null;
}

describe('scannerNewsStore', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    resetScannerNewsForTests();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    resetScannerNewsForTests();
  });

  it('returns empty map when source mismatches (sample/live isolation)', async () => {
    const map = new Map([['SMTI', '2026-07-30T12:00:00Z']]);
    setScannerNews('sample', map);

    let liveSize = -1;
    let liveHas = false;
    let sampleSize = -1;
    let sampleHas = false;

    await act(async () => {
      root.render(
        createElement(
          'div',
          null,
          createElement(Probe, {
            expected: 'live',
            onMap: (size: number, has: boolean) => {
              liveSize = size;
              liveHas = has;
            },
          }),
          createElement(Probe, {
            expected: 'sample',
            onMap: (size: number, has: boolean) => {
              sampleSize = size;
              sampleHas = has;
            },
          }),
        ),
      );
    });

    expect(liveSize).toBe(0);
    expect(liveHas).toBe(false);
    expect(sampleSize).toBe(1);
    expect(sampleHas).toBe(true);
  });
});
