/**
 * @vitest-environment jsdom
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  formatScannerWindowTitle,
  formatTraderDocumentTitle,
} from '../../electron/appTitle.mjs';
import { releaseTagFromText } from '../../electron/releaseTag.mjs';
import { novaRendererReleaseTag } from './novaReleaseTag';
import { useNovaDeskWindowTitle, useNovaWindowTitle } from './useNovaWindowTitle';

const repoVersion = releaseTagFromText(
  readFileSync(
    path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../VERSION'),
    'utf8',
  ),
);

describe('useNovaWindowTitle', () => {
  it('writes a real VERSION tag onto scanner and trader titles', () => {
    const tag = novaRendererReleaseTag();
    expect(tag).toMatch(/^v\d+$/);
    expect(tag).toBe(repoVersion);

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
