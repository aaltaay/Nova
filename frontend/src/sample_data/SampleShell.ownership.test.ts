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

  it('owns its workspace: the sample provider wraps the shell (#449)', () => {
    const src = readFileSync(join(here, 'SampleShell.tsx'), 'utf8');
    expect(src).toMatch(/<SampleWorkspaceProvider>[\s\S]*<SampleShellInner \/>[\s\S]*<\/SampleWorkspaceProvider>/);
  });

  it('marks both sample windows with the marketing badge (#357, #449)', () => {
    const src = readFileSync(join(here, 'SampleShell.tsx'), 'utf8');
    expect(src).toMatch(/import \{ SampleModeBadge \} from '\.\/SampleModeBadge'/);
    // The main desk (Trader, Desk and dashboard share one strip above them)
    // and a sample pop-out each render it.
    const rendered = src.match(/<SampleModeBadge\b/g) ?? [];
    expect(rendered).toHaveLength(2);
    expect(src).toMatch(
      /source="sample-trader"[\s\S]*source="sample-dashboard"/,
    );
  });
});
