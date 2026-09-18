import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));

function css(rel: string): string {
  return readFileSync(resolve(here, rel), 'utf8');
}

describe('Electron-safe viewport locks', () => {
  it('does not pin body to 100dvh (Electron can clip the desk to black)', () => {
    const dock = css('../hod_momo/hodMomoDock.css');
    const stock = css('stock-view.css');
    expect(dock).not.toMatch(/body:has\(\.nova-app-stack\)\s*\{[^}]*100dvh/s);
    expect(stock).not.toMatch(
      /body:has\(\.nova-shell--ticker-detail\)\s*\{[^}]*100dvh/s,
    );
    expect(dock).toMatch(/body:has\(\.nova-app-stack\)\s*\{[^}]*height:\s*100%/s);
    expect(stock).toMatch(
      /body:has\(\.nova-shell--ticker-detail\)\s*\{[^}]*height:\s*100%/s,
    );
    const tokens = css('tokens-shell.css');
    expect(tokens).toMatch(/html\s*\{[^}]*height:\s*100%/s);
    expect(tokens).toMatch(/html\s*\{[^}]*min-height:\s*100%/s);
  });
});
