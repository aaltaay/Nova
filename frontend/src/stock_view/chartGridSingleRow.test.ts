/**
 * The Trader's chart rows (operator report 2026-10-15): with the 10-Second pane hidden, Full Day is
 * the bottom row's only pane and must span it. The Trader's two-column row rule outranked
 * `.chart-grid__row--single`, so Full Day took the left half beside an empty black half.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const terminal = readFileSync(resolve(here, './stockViewTerminal.css'), 'utf8').replace(/\r\n/g, '\n');

const ROW = '.stock-view-page .stock-view-charts .chart-grid__row {';
const SINGLE = '.stock-view-page .stock-view-charts .chart-grid__row--single {\n';

describe('Trader chart grid: a single bottom pane spans the row', () => {
  it('follows every two-column row rule with a one-column single-row rule', () => {
    let from = 0;
    let rows = 0;
    for (;;) {
      const at = terminal.indexOf(ROW, from);
      if (at < 0) break;
      rows += 1;
      const single = terminal.indexOf(SINGLE, at);
      expect(single, `no single-row rule after the row rule at ${at}`).toBeGreaterThan(at);
      const next = terminal.indexOf(ROW, at + ROW.length);
      if (next >= 0) expect(single).toBeLessThan(next);
      expect(terminal.slice(single, terminal.indexOf('}', single))).toContain('grid-template-columns: 1fr;');
      from = at + ROW.length;
    }
    expect(rows).toBeGreaterThan(0);
  });
});
