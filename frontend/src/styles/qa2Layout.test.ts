/**
 * Layout contracts from the second QA pass (2026-09-22) -- jsdom does no
 * layout, so these read the stylesheets. Each block names the finding it
 * holds; the harness screenshots in the PR show the result at 1280 / 1440 /
 * 1920 / 2560.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
// CRLF on a Windows checkout must not break the matches.
const read = (rel: string) => readFileSync(resolve(here, rel), 'utf8').replace(/\r\n/g, '\n');

const responsive = read('./global-app-bar-responsive.css');
const scannerDesk = read('../scanner/scannerDesk.css');
const railDepth = read('../stock_view/stockViewRailDepth.css');
const terminal = read('../stock_view/stockViewTerminal.css');
const narrow = read('../stock_view/stockViewNarrow.css');
const quickTrades = read('../stock_view/stockViewQuickTrades.css');
const marketData = read('../ibkr/marketData.css');
const timeSales = read('../ibkr/timeSales.css');
const level2 = read('../ibkr/level2Montage.css');
const tickerChart = read('../chart/tickerChart.css');
const hodDock = read('../hod_momo/hodMomoDock.css');
const tabs = read('../stock_view/stockViewTabs.css');
const dock = read('../stock_view/openOrdersDock.css');
const navRail = read('./navRail.css');

/** The body of the first `@media (<query>) {` / `@container <query> {` block, brace-matched. */
function block(css: string, head: string): string {
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

const TWO_RECS = '.global-app-bar__primary:has(.global-app-bar__rec ~ .global-app-bar__rec)';
const THREE_RECS = '.global-app-bar__primary:has(.global-app-bar__rec ~ .global-app-bar__rec ~ .global-app-bar__rec)';

describe('D1: the header sheds per REC chip, never the KILL, search, pill, padlock or gear', () => {
  it('drops the REC times with three recordings at 1920 and with two at 1600', () => {
    expect(block(responsive, '@media (max-width: 1920px) {')).toContain(`${THREE_RECS} .global-app-bar__rec-time`);
    const at1600 = block(responsive, '@media (max-width: 1600px) {');
    expect(at1600).toContain(`${TWO_RECS} .global-app-bar__rec-time`);
    expect(at1600).toContain(`${TWO_RECS} .global-app-bar__metric--day`);
  });

  it('drops the REC word with three at 1440 and TAV with two at 1280', () => {
    expect(block(responsive, '@media (max-width: 1440px) {')).toContain(`${THREE_RECS} .global-app-bar__rec-role`);
    expect(block(responsive, '@media (max-width: 1280px) {')).toContain(`${TWO_RECS} .global-app-bar__metric--tav`);
  });

  it('keeps the chip dot and symbol: no rule hides a whole REC chip', () => {
    // The subject of every hiding selector: its last compound, outside :has().
    const hidden: string[] = [];
    for (const m of responsive.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      if (!/display:\s*none/.test(m[2])) continue;
      for (const selector of m[1].split(',')) {
        const flat = selector.replace(/\([^()]*(\([^()]*\))*[^()]*\)/g, '()').trim();
        hidden.push(flat.split(/\s+/).pop() ?? '');
      }
    }
    expect(hidden.length).toBeGreaterThan(0);
    expect(hidden).not.toContain('.global-app-bar__rec');
    expect(hidden).not.toContain('.global-app-bar__rec-symbol');
  });
});

describe('D2: the Scanner row actions stick to the visible board edge', () => {
  it('lets a hovered / selected / focused row\'s host cell stick right and stop clipping', () => {
    const rule = /\.table-wrapper--scanner \.scanner-row:hover > \.scanner-row-actions-host,[^{]*row-selected[^{]*focus-within[^{]*\{([^}]*)\}/.exec(scannerDesk);
    expect(rule, 'sticky host rule').not.toBeNull();
    expect(rule![1]).toMatch(/position:\s*sticky/);
    expect(rule![1]).toMatch(/right:\s*0/);
    expect(rule![1]).toMatch(/overflow:\s*visible/);
    // The header stays above a sticky cell scrolling under it.
    expect(scannerDesk).toMatch(/\.table-wrapper--scanner thead th \{\s*z-index:\s*3;/);
  });
});

describe('D3 + R28: the rail\'s Level 2 and Time & Sales', () => {
  it('imports the rail sheet at the top of the terminal sheet (features layer)', () => {
    expect(terminal).toMatch(/^[\s\S]*?\*\/\n@import "\.\/stockViewRailDepth\.css";/);
    expect(marketData).toMatch(/@import "\.\/timeSales\.css";\n@import "\.\/level2Montage\.css";/);
  });

  it('gives Time & Sales the width Time + Price + Size need and Level 2 the rest', () => {
    expect(railDepth).toMatch(/\.sv-rail \.sv-depth-and-tape \{\s*grid-template-columns:\s*minmax\(0, 1fr\) clamp\(126px, 40%, 220px\);/);
  });

  it('never collapses the tape\'s Price column: every column has a width and a gap', () => {
    const narrowTape = block(timeSales, '@container md-pane (max-width: 279px) {');
    expect(narrowTape).toMatch(/grid-template-columns:\s*7\.6ch minmax\(0, 0\.9fr\) minmax\(0, 1\.1fr\)/);
    expect(narrowTape).toMatch(/column-gap:\s*4px/);
    expect(timeSales).not.toMatch(/68px minmax\(0, 1fr\) 40px/);
  });

  it('keeps a size and its price apart, and drops MM in a narrow book', () => {
    expect(level2).toMatch(/\.das-l2-colhead,\n\.das-l2-row \{\s*column-gap:\s*4px;/);
    const narrowBook = block(level2, '@container md-pane (max-width: 259px) {');
    expect(narrowBook).toMatch(/\.das-l2-mm/);
    expect(narrowBook).toMatch(/display:\s*none/);
  });

  it('puts the six quote stats on two short lines', () => {
    expect(railDepth).toMatch(/\.sv-quote-stats\.compact-grid \{\s*grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\)/);
  });
});

describe('D5: a narrow Trader column keeps its controls', () => {
  it('wraps the desk chart toolbar instead of hiding controls past a scroll box', () => {
    expect(terminal).toContain('@import "./stockViewNarrow.css";');
    expect(narrow).toMatch(/\.chart-desk-toolbar__scroll \{\s*flex-wrap:\s*wrap;[\s\S]*?overflow-x:\s*visible;/);
  });

  it('keeps the drawer row inside its column', () => {
    expect(dock).toMatch(/\.sv-open-orders-dock__bar \{[^}]*overflow:\s*hidden;/);
    expect(dock).toMatch(/\.sv-open-orders-dock__tabs \{[^}]*flex:\s*0 1 auto;/);
  });
});

describe('D6: the oscillator pane x takes its clicks', () => {
  it('stacks the chart body under the label', () => {
    expect(tickerChart).toMatch(/\.chart-oscillator-body \{\s*position:\s*relative;\s*z-index:\s*0;/);
    expect(tickerChart).toMatch(/\.chart-oscillator-pane > \.chart-oscillator-label \{\s*z-index:\s*3;/);
  });
});

describe('D9: the HOD strip header in a narrow board column', () => {
  it('never shrinks the HOD Momo / Running Up segments or the feed word', () => {
    expect(hodDock).toMatch(/\.hod-strip__head \.hod-momo-dock__modes,\n\.hod-strip__head \.hod-strip__feed \{\s*flex-shrink:\s*0;/);
    const narrowStrip = block(hodDock, '@container hod-strip (max-width: 620px) {');
    expect(narrowStrip).toContain('.hod-strip__since');
    expect(narrowStrip).toContain('.hod-strip__integrity-text');
  });
});

describe('D12: the tab strip keeps "+" and the Sim session menu', () => {
  it('never shrinks the scrubber below its controls, and never wraps it', () => {
    expect(tabs).toMatch(/\.sv-tab-strip__trailing \{[^}]*min-width:\s*min-content;/);
    expect(tabs).toMatch(/\.sv-tab-strip__trailing > \.sim-strip \{\s*flex-wrap:\s*nowrap;/);
  });
});

describe('V28: an open rail foot item keeps its width', () => {
  it('does not bold the open Settings item into truncation', () => {
    expect(navRail).toMatch(/\.nav-rail__foot \.nav-rail__item\.is-active \{\s*font-weight:\s*inherit;/);
  });
});

describe('D14: Quick Trades labels wrap between words, never inside one', () => {
  it('imports the Quick Trades sheet at the top of the terminal sheet (features layer)', () => {
    expect(terminal.indexOf('@import "./stockViewQuickTrades.css";')).toBeGreaterThanOrEqual(0);
    expect(terminal.indexOf('@import "./stockViewQuickTrades.css";')).toBeLessThan(terminal.indexOf('.stock-view-page {'));
  });

  it('never breaks anywhere inside a word, and ellipsizes a word too wide for its button', () => {
    expect(quickTrades).not.toMatch(/overflow-wrap:\s*anywhere|word-break:\s*break-all/);
    expect(terminal).not.toMatch(/\.nova-qt__btn > span\b/);
    const label = quickTrades.slice(quickTrades.indexOf('.nova-qt__btn > .nova-qt__label {'));
    expect(label).toMatch(/^[^}]*-webkit-line-clamp:\s*2;/);
    expect(label).toMatch(/^[^}]*overflow-wrap:\s*normal;/);
    const word = quickTrades.slice(quickTrades.indexOf('.nova-qt__label > .nova-qt__word {'));
    expect(word).toMatch(/^[^}]*white-space:\s*nowrap;/);
    expect(word).toMatch(/^[^}]*text-overflow:\s*ellipsis;/);
  });

  it('lets the type follow the button width, never below 7 px', () => {
    expect(quickTrades).toMatch(/\.nova-qt__btn\[data-kind\] \{\s*container-type:\s*inline-size;/);
    expect(quickTrades).toMatch(/font-size:\s*clamp\(7px, \d+cqi, 9px\);/);
  });
});
