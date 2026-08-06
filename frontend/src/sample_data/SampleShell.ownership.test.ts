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
});
