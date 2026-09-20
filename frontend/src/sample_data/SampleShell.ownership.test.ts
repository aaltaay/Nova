/**
 * @vitest-environment node
 * Guard: GlobalAppBar requires IbkrAccountProvider; sample must mount it.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));

describe('SampleShell ownership', () => {
  it('mounts IbkrAccountProvider under SampleDataProvider', () => {
    const src = readFileSync(join(here, 'SampleShell.tsx'), 'utf8');
    expect(src).toMatch(/IbkrAccountProvider/);
    expect(src).toMatch(
      /SampleDataProvider[\s\S]*IbkrAccountProvider[\s\S]*SampleShellInner/,
    );
  });

  it('marks both sample branches with the marketing badge (#357)', () => {
    const src = readFileSync(join(here, 'SampleShell.tsx'), 'utf8');
    expect(src).toMatch(/import \{ SampleModeBadge \} from '\.\/SampleModeBadge'/);
    // Trader branch and dashboard branch each render it -- the Trader route
    // was previously unmarked because the strip lived in the dashboard column.
    const rendered = src.match(/<SampleModeBadge\b/g) ?? [];
    expect(rendered).toHaveLength(2);
    expect(src).toMatch(
      /source="sample-trader"[\s\S]*source="sample-dashboard"/,
    );
  });
});
