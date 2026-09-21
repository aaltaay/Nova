/**
 * The header's status chips must never overprint the brand and nav.
 *
 * `.global-app-bar__primary` is a grid whose middle column is `minmax(0, 1fr)`.
 * A status cluster that cannot shrink or wrap overflows that column, and under
 * `justify-content: flex-end` the overflow goes *leftward*, painting over the
 * brand and the Scanner/Trader nav. Whether it fits depends on live values --
 * Day P&L, Net Liq, which badges are showing -- so the width-based media
 * queries cannot catch it; only shrink + wrap can.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(resolve(here, './global-app-bar.css'), 'utf8');

/** The declaration block for exactly one selector. */
function block(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = css.match(new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`, 'm'));
  if (!match) throw new Error(`no rule for ${selector}`);
  return match[1];
}

describe('global app bar status cluster', () => {
  it('keeps the middle column able to shrink below its content', () => {
    expect(block('.global-app-bar__primary')).toMatch(/grid-template-columns:[^;]*minmax\(\s*0/);
    expect(block('.global-app-bar__center')).toMatch(/min-width:\s*0/);
  });

  it('lets the status cluster shrink instead of overflowing its column', () => {
    const status = block('.global-app-bar__status');
    expect(status).toMatch(/flex:\s*0\s+1\s+auto/);
    expect(status).not.toMatch(/flex:\s*0\s+0\s+auto/);
    expect(status).toMatch(/min-width:\s*0/);
  });

  it('wraps chips onto another line rather than over the brand and nav', () => {
    expect(block('.global-app-bar__status')).toMatch(/flex-wrap:\s*wrap/);
    const cluster = block('.global-app-bar__status .status-cluster');
    expect(cluster).toMatch(/flex-wrap:\s*wrap/);
    expect(cluster).not.toMatch(/flex-wrap:\s*nowrap/);
  });

  it('keeps individual chips unsquished, so wrapping is what gives way', () => {
    expect(css).toMatch(/\.global-app-bar__status \.status-chip[^{]*\{[^}]*flex-shrink:\s*0/s);
  });
});
