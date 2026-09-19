/**
 * @vitest-environment jsdom
 */
import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  formatScannerWindowTitle,
  formatTraderDocumentTitle,
} from '../../electron/appTitle.mjs';
import { novaRendererReleaseTag } from './novaReleaseTag';
import { useNovaDeskWindowTitle, useNovaWindowTitle } from './useNovaWindowTitle';

// VERSION is a build artifact (#344), so this asserts the tag vite injected --
// resolved from the generated file or from git -- rather than reading a repo file.
describe('useNovaWindowTitle', () => {
  it('writes a real VERSION tag onto scanner and trader titles', () => {
    const tag = novaRendererReleaseTag();
    expect(tag).toMatch(/^v\d+$/);

    const { rerender } = renderHook(
      ({ active, symbol }: { active: boolean; symbol: string | null }) =>
        useNovaWindowTitle(active, symbol),
      { initialProps: { active: false, symbol: null } },
    );
    expect(document.title).toBe(formatScannerWindowTitle(tag));

    rerender({ active: true, symbol: 'AAPL' });
    expect(document.title).toBe(formatTraderDocumentTitle('AAPL', tag));
  });

  it('sets a sample trader title from ?view=sample&symbol=SMPL', () => {
    const tag = novaRendererReleaseTag();
    window.history.replaceState({}, '', '/?view=sample&symbol=SMPL');
    renderHook(() => useNovaDeskWindowTitle(true, false, null));
    expect(document.title).toBe(formatTraderDocumentTitle('SMPL', tag));
  });
});
