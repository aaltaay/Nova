/**
 * Every ticker opens the Trader (operator ask, 2026-10-15: "make this a shortcut for every ticker in the
 * software ... all using a single source of truth").
 *
 * Parses every component under src/ and fails on a ticker drawn as plain JSX text -- `{row.symbol}`,
 * `{sym}`, `{ticker}` -- unless it sits inside `TickerLink` (components/TickerLink.tsx, the one source), inside
 * a button or link that already opens something (a button holds no button), in an `<option>`, or is on the
 * list below with the reason it is not a door to the Trader.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
/** A ticker under one of these is already clickable, or cannot hold a button. */
const COVERED_BY = new Set(['TickerLink', 'button', 'a', 'option', 'select', 'text', 'textarea', 'title']);
/** The last name of an expression that is a ticker: `symbol`, `sym`, `ticker`, `selectedSymbol`... */
const TICKER_NAME = /^(symbol|sym|ticker|[a-z]+Symbol)$/;

/** Plain on purpose: file (from src/) -> the expressions it may draw as text, and why. */
const PLAIN_ON_PURPOSE: Record<string, { exprs: string[]; why: string }> = {
  'stock_read/HistoryTab.tsx': { exprs: ['h.symbol'], why: 'the Trader tab of that symbol: you are on it' },
  'stock_read/ReadSheet.tsx': { exprs: ['ctx.symbol'], why: 'the Trader tab of that symbol: you are on it' },
  'stock_read/ExitSheet.tsx': { exprs: ['ctx.symbol'], why: 'the Trader tab of that symbol: you are on it' },
  'stock_read/HeldCard.tsx': { exprs: ['ctx.symbol'], why: 'the Trader tab of that symbol: you are on it' },
  'stock_read/WhoTradesRow.tsx': { exprs: ['sym'], why: 'the Trader tab of that symbol: you are on it' },
  'heat_map/HeatMapView.tsx': { exprs: ['sym'], why: 'the heat map over that symbol\'s own Trader tab: you are on it' },
  'stock_view/FloatDeskChrome.tsx': { exprs: ['sym'], why: 'the Trader window\'s own title' },
  'stock_view/StockViewDockFooter.tsx': { exprs: ['symbol', 'sym'], why: 'the Trader tab\'s own footer' },
  'stock_view/StockViewTabStrip.tsx': { exprs: ['symbol'], why: 'the Trader\'s own tab' },
  'stock_view/FocusRailPane.tsx': { exprs: ['row.symbol'], why: 'the whole Focus rail row opens it' },
  'stock_view/StockViewQuotePrice.tsx': { exprs: ['detail.symbol'], why: 'the Trader tab\'s own quote' },
  'bot/BotSymbolMenu.tsx': { exprs: ['symbol'], why: 'the right-click menu\'s caption: the ticker it opened on is the link' },
  'ibkr/WorkingOrderMenu.tsx': { exprs: ['order.symbol'], why: 'the order menu\'s caption, opened on the order\'s own row' },
  'followed_traders/parts.tsx': { exprs: ['symbol'], why: 'Ticker\'s plain branch: the page was given no Trader' },
  'market_board/parts.tsx': { exprs: ['symbol'], why: 'Sym\'s plain branch: the card was given no Trader' },
  'clips/ClipExportDialog.tsx': { exprs: ['row.symbol'], why: 'names the clip being exported' },
  'clips/ClipFrame.tsx': { exprs: ['symbol'], why: 'drawn into the clip\'s frame' },
  'clips/ClipTimeline.tsx': { exprs: ['symbol'], why: 'names what the clip shows' },
  'clips/RecordMenu.tsx': { exprs: ['symbol'], why: 'the Record menu on that symbol\'s own Trader tab' },
  'components/SidePanel.tsx': { exprs: ['selectedSymbol'], why: 'status words; the panel has its own Open button' },
  'cryptos/CandleChart.tsx': { exprs: ['data.symbol'], why: 'a coin: the Trader opens stocks' },
  'cryptos/CoinsCard.tsx': { exprs: ['c.symbol'], why: 'a coin: the Trader opens stocks' },
  'cryptos/LowerCards.tsx': { exprs: ['f.symbol', 'n.symbol'], why: 'a coin: the Trader opens stocks' },
};

interface Finding {
  where: string;
  expr: string;
}

function componentFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) componentFiles(full, out);
    else if (entry.name.endsWith('.tsx') && !entry.name.endsWith('.test.tsx')) out.push(full);
  }
  return out;
}

function tickerExpr(expr: ts.Expression | undefined): boolean {
  if (!expr) return false;
  let e: ts.Expression = expr;
  while (ts.isNonNullExpression(e) || ts.isParenthesizedExpression(e)) e = e.expression;
  if (ts.isIdentifier(e)) return TICKER_NAME.test(e.text);
  if (ts.isPropertyAccessExpression(e)) {
    // A column-header constant (`FOCUS_RAIL_ALERT_COLS.symbol`) is a word, not a ticker.
    if (ts.isIdentifier(e.expression) && /^[A-Z0-9_]+$/.test(e.expression.text)) return false;
    return TICKER_NAME.test(e.name.text);
  }
  return false;
}

function covered(node: ts.Node, sf: ts.SourceFile): boolean {
  for (let p: ts.Node | undefined = node.parent; p; p = p.parent) {
    if (ts.isJsxElement(p) && COVERED_BY.has(p.openingElement.tagName.getText(sf))) return true;
  }
  return false;
}

function findPlainTickers(files: string[]): Finding[] {
  const found: Finding[] = [];
  for (const file of files) {
    const rel = path.relative(SRC, file).replace(/\\/g, '/');
    const text = fs.readFileSync(file, 'utf8');
    const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const allowed = new Set(PLAIN_ON_PURPOSE[rel]?.exprs ?? []);
    const visit = (node: ts.Node) => {
      // A JSX child `{...}` (an attribute's value is a JsxExpression under a JsxAttribute, not a child).
      if (ts.isJsxExpression(node) && !ts.isJsxAttribute(node.parent) && tickerExpr(node.expression)) {
        const expr = node.expression!.getText(sf).replace(/!$/, '');
        if (!allowed.has(expr) && !covered(node, sf)) {
          const line = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
          found.push({ where: `${rel}:${line}`, expr });
        }
      }
      ts.forEachChild(node, visit);
    };
    visit(sf);
  }
  return found;
}

describe('every ticker opens the Trader', () => {
  // Parses every component file with the TypeScript compiler: see ux/whyCoverage.test.ts for the timeout.
  it('no component draws a ticker as plain text', () => {
    const plain = findPlainTickers(componentFiles(SRC));
    const report = plain.map(f => `  ${f.where} {${f.expr}}`).join('\n');
    expect(plain, `Tickers drawn as plain text -- wrap them in <TickerLink> (components/TickerLink.tsx):\n${report}`)
      .toEqual([]);
  }, 30_000);

  it('every plain-on-purpose entry is still in its file', () => {
    const stale = Object.entries(PLAIN_ON_PURPOSE).filter(([rel]) => !fs.existsSync(path.join(SRC, rel)));
    expect(stale.map(([rel]) => rel)).toEqual([]);
  });

  it('the parser sees a bare ticker and accepts TickerLink, a button and an option', () => {
    const tmp = path.join(os.tmpdir(), `ticker-link-coverage-probe-${process.pid}.tsx`);
    fs.writeFileSync(tmp, [
      'export const A = () => <td>{row.symbol}</td>;',
      'export const B = () => <td><TickerLink symbol={row.symbol}>{row.symbol}</TickerLink></td>;',
      'export const C = () => <button>{sym}</button>;',
      'export const D = () => <option>{ticker}</option>;',
      'export const E = () => <b>{selectedSymbol!}</b>;',
      'export const F = () => <th>{COLS.symbol}</th>;',
      'export const G = () => <td data-x={row.symbol}>{row.name}</td>;',
    ].join('\n'));
    try {
      const found = findPlainTickers([tmp]).map(f => `${f.where.split(':').pop()} ${f.expr}`);
      expect(found).toEqual(['1 row.symbol', '5 selectedSymbol']);
    } finally {
      fs.rmSync(tmp, { force: true });
    }
  });
});
