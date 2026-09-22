/**
 * The global bar is one row that never paints over itself.
 *
 * `.global-app-bar__primary` is a flex row: the left and right clusters split
 * the free space so the ticker search sits centred, the search is the only
 * element that gives way (`flex: 0 1 auto; min-width: 0`), and the clusters
 * keep their chips whole (`flex-wrap: nowrap`, `flex-shrink: 0` on the chips).
 * Whether everything fits depends on live values -- Day P&L, the account id,
 * how many REC chips are up -- so the width-based sheet sheds low-value chrome
 * in a fixed order instead of letting chips overprint the brand.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(resolve(here, './global-app-bar.css'), 'utf8');
const responsive = readFileSync(resolve(here, './global-app-bar-responsive.css'), 'utf8');

/** The declaration block for exactly one selector (or selector list). */
function block(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = css.match(new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`, 'm'));
  if (!match) throw new Error(`no rule for ${selector}`);
  return match[1];
}

describe('global app bar primary row', () => {
  it('is one flex row that does not wrap', () => {
    const primary = block('.global-app-bar__primary');
    expect(primary).toMatch(/display:\s*flex/);
    expect(primary).toMatch(/flex-wrap:\s*nowrap/);
    expect(primary).toMatch(/min-width:\s*0/);
  });

  it('splits the free space between the two clusters so the search sits centred', () => {
    const sides = block('.global-app-bar__left,\n.global-app-bar__right');
    expect(sides).toMatch(/flex:\s*1\s+1\s+0/);
    expect(sides).toMatch(/flex-wrap:\s*nowrap/);
    expect(css).toMatch(/\n\.global-app-bar__right \{[^}]*justify-content:\s*flex-end/);
  });

  it('lets only the centre search give way', () => {
    const center = block('.global-app-bar__center');
    expect(center).toMatch(/flex:\s*0\s+1\s+auto/);
    expect(center).toMatch(/min-width:\s*0/);
    const search = block('.global-app-bar__search');
    expect(search).toMatch(/width:\s*260px/);
    expect(search).toMatch(/max-width:\s*100%/);
    expect(search).toMatch(/min-width:/);
  });

  it('keeps the chips whole, so shedding -- not squishing -- is what gives way', () => {
    expect(block('.global-app-bar__session,\n.global-app-bar__conn,\n.global-app-bar__rec')).toMatch(
      /flex-shrink:\s*0/,
    );
    expect(block('.global-app-bar__emergency-kill')).toMatch(/flex-shrink:\s*0/);
    expect(block('.global-app-bar__brand')).toMatch(/flex-shrink:\s*0/);
    expect(block('.global-app-bar__primary .header-market-clock')).toMatch(/flex-shrink:\s*0/);
  });

  it('sheds low-value chrome in a fixed order and never the KILL, search, pill, padlock or gear', () => {
    const at = (px: number) => {
      const m = responsive.match(new RegExp(`@media \\(max-width: ${px}px\\) \\{([\\s\\S]*?)\\n\\}`));
      if (!m) throw new Error(`no ${px}px breakpoint`);
      return m[1];
    };
    expect(at(1400)).toContain('.global-app-bar__rec-time');
    expect(at(1280)).toContain('.global-app-bar__session');
    expect(at(1100)).toContain('.header-market-clock');
    expect(at(900)).toContain('.global-app-bar__wordmark');
    for (const keep of [
      '__emergency-kill',
      '__conn',
      'gw-mode-capsule',
      '__search-input',
      '__account-pill',
      '__trade-lock',
      '__gear',
    ]) {
      expect(responsive, `${keep} must survive every breakpoint`).not.toMatch(
        new RegExp(`${keep.replace(/[-]/g, '\\-')}[^{]*\\{[^}]*display:\\s*none`),
      );
    }
  });
});
