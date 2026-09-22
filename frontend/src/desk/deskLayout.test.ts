/**
 * Desk board geometry contract (QA V18 / V37). jsdom does no layout, so these
 * read the stylesheets: the board fits inside its column, its pinned columns
 * fit inside the board beside a scrollbar at both board widths, the Float
 * cells keep their grid slot when hidden, and the row actions are not left up
 * on a row a mouse click focused.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { DESK_BOARD_NARROW_WIDTH_PX, DESK_BOARD_WIDTH_PX } from '../constantGroups/desk';

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel: string) => readFileSync(resolve(here, rel), 'utf8').replace(/\r\n/g, '\n');
const deskCss = read('./desk.css');
const boardCss = read('./deskBoard.css');
const tokensCss = read('../styles/tokens-shell.css');

const REM_PX = 16;
/** Board border + table-wrapper border, both sides (measured: 480 -> 478 -> 476). */
const BOARD_AND_WRAPPER_BORDERS_PX = 4;
/** The state column's "—" plus its 0.35rem side padding. */
const STATE_MIN_PX = 18;
const PINNED = ['rownum', 'symbol', 'price', 'gap_percent', 'volume', 'rel_volume', 'float', 'catalyst'];

/** The body of `@media (<query>) { ... }`, brace-matched. */
function mediaBlock(css: string, query: string): string {
  const head = `@media (${query}) {`;
  const start = css.indexOf(head);
  if (start < 0) throw new Error(`no ${head}`);
  let depth = 0;
  for (let i = start + head.length - 1; i < css.length; i += 1) {
    if (css[i] === '{') depth += 1;
    if (css[i] === '}') {
      depth -= 1;
      if (depth === 0) return css.slice(start, i + 1);
    }
  }
  throw new Error(`unclosed ${head}`);
}

/** The first declaration block whose selector list names exactly `selector`. */
function ruleBody(css: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const m = new RegExp(`${escaped}(?![-\\w])[^{}]*\\{([^}]*)\\}`).exec(css);
  if (!m) throw new Error(`no rule for ${selector}`);
  return m[1];
}

function pinnedPx(block: string, key: string): number {
  const m = new RegExp(`\\.scanner-col--${key}\\b[^{}]*\\{\\s*width:\\s*([\\d.]+)(rem)?\\s*;`).exec(block);
  if (!m) throw new Error(`no pinned width for ${key}`);
  return Number(m[1]) * (m[2] ? REM_PX : 1);
}

function columnPaddingPx(): number {
  const body = ruleBody(deskCss, '.desk-page .desk-page__column');
  const m = /padding:\s*([\d.]+)rem\s+([\d.]+)rem\s+([\d.]+)rem\s+([\d.]+)rem/.exec(body);
  if (!m) throw new Error('desk column padding is not four rem values');
  return (Number(m[2]) + Number(m[4])) * REM_PX;
}

function scrollbarPx(): number {
  const m = /--scrollbar-size:\s*(\d+)px/.exec(tokensCss);
  if (!m) throw new Error('no --scrollbar-size token');
  return Number(m[1]);
}

describe('desk board geometry', () => {
  const narrow = mediaBlock(boardCss, 'max-width: 1600px');
  const base = boardCss.replace(narrow, '');

  it('sizes the column border-box, so its padding never pushes the board under the Trader', () => {
    expect(ruleBody(deskCss, '.desk-page .desk-page__column')).toMatch(/box-sizing:\s*border-box/);
  });

  it.each([
    ['wide', DESK_BOARD_WIDTH_PX, base],
    ['narrow (<= 1600 px)', DESK_BOARD_NARROW_WIDTH_PX, narrow],
  ])('fits the pinned columns inside the %s board beside a scrollbar', (_label, columnPx, block) => {
    const table = columnPx - columnPaddingPx() - BOARD_AND_WRAPPER_BORDERS_PX - scrollbarPx();
    const pinned = PINNED.reduce((sum, key) => sum + pinnedPx(block, key), 0);
    expect(pinned + STATE_MIN_PX).toBeLessThanOrEqual(table);
  });

  it('keeps the hidden Float cells in the row so later cells keep their columns', () => {
    const cells = ruleBody(narrow, 'td.scanner-col--float');
    expect(cells).not.toMatch(/display:\s*none/);
    expect(cells).toMatch(/visibility:\s*hidden/);
    expect(cells).toMatch(/padding:\s*0/);
    expect(pinnedPx(narrow, 'float')).toBe(0);
  });

  it('drops the clipped State label on the narrow board, keeping the header title', () => {
    expect(ruleBody(narrow, 'th.scanner-col--state')).toMatch(/color:\s*transparent/);
  });

  it('swaps in the short action labels on the narrow board', () => {
    expect(ruleBody(boardCss, '.desk-board__act-text--short')).toMatch(/display:\s*none/);
    expect(ruleBody(narrow, '.desk-board__act-text')).toMatch(/display:\s*none/);
    expect(ruleBody(narrow, '.desk-board__act-text--short')).toMatch(/display:\s*inline/);
  });

  it('shows row actions on hover or keyboard focus, never left up by a mouse click', () => {
    expect(boardCss).not.toMatch(/\.desk-board__(row|acts):focus-within/);
    expect(boardCss).toMatch(/\.desk-board__row:hover\s+\.desk-board__acts/);
    expect(boardCss).toMatch(/\.desk-board__row:focus-visible\s+\.desk-board__acts/);
    expect(boardCss).toMatch(/\.desk-board__acts:has\(:focus-visible\)/);
  });

  it('hides the Catalyst content the actions cover while they show', () => {
    expect(ruleBody(boardCss, '.desk-board__row:hover .scanner-col--catalyst > *')).toMatch(/visibility:\s*hidden/);
  });

  it('lets the gap bar give way before the figure is clipped', () => {
    expect(ruleBody(boardCss, '.desk-board__bar')).toMatch(/flex:\s*0 1 30px/);
    expect(ruleBody(boardCss, '.desk-board__bar')).toMatch(/min-width:\s*0/);
    expect(ruleBody(boardCss, '.desk-board__gap-num')).toMatch(/flex:\s*none/);
  });
});
