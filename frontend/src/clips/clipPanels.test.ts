/**
 * A clip's blur is only as good as its selector (ADR 039). The order ticket's
 * once named `order-ticket`, which only a test mock renders: the export dialog
 * said the ticket was blurred and it was not. Every panel a clip reports and
 * can blur must name an element a real component renders.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { CLIP_PANELS } from '../../electron/clipPlan.mjs';
import { CLIP_PANEL_LABELS, CLIP_PANEL_SELECTORS, CLIP_PRIVATE_PANELS } from './clipsConstants';

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function componentSources(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) componentSources(full, out);
    else if (entry.name.endsWith('.tsx') && !entry.name.endsWith('.test.tsx')) out.push(fs.readFileSync(full, 'utf8'));
  }
  return out;
}

describe('clip panels', () => {
  const sources = componentSources(SRC);

  it('are the ones the main process reads', () => {
    expect(Object.keys(CLIP_PANEL_SELECTORS).sort()).toEqual([...CLIP_PANELS].sort());
    expect(Object.keys(CLIP_PANEL_LABELS).sort()).toEqual([...CLIP_PANELS].sort());
    for (const id of CLIP_PRIVATE_PANELS) expect(CLIP_PANELS).toContain(id);
  });

  it.each(Object.entries(CLIP_PANEL_SELECTORS))('%s names elements a component renders', (_id, selector) => {
    for (const part of selector.split(',').map((x) => x.trim())) {
      const testId = /^\[data-testid="([^"]+)"\]$/.exec(part)?.[1];
      expect(testId, `${part} is not a data-testid selector`).toBeTruthy();
      const rendered = sources.some((s) => s.includes(`data-testid="${testId}"`) || s.includes(`testId="${testId}"`));
      expect(rendered, `no component renders data-testid="${testId}"`).toBe(true);
    }
  });
});
