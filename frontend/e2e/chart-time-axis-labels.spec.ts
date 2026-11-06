import { expect, test, type Page } from '@playwright/test';
import type { IChartApi } from 'lightweight-charts';

/**
 * #459 (5b): lightweight-charts centres each time-axis label on its tick, so a
 * tick near either edge of a freely scrolling chart drew half a label --
 * `2026` read `026`, `10:00 AM` read `10:00 A`. On Nova's own chart instance,
 * at narrow and wide panes and DPR 1 / 1.5, swept across scroll positions,
 * every time label it draws lies wholly inside the axis, and labels still draw.
 */
const WIDTHS = [320, 480, 800];
const DPRS = [1, 1.5];

type Drawn = { text: string; left: number; right: number; axis: number };

declare global {
  interface Window { __axisLabels?: Drawn[]; __chart?: IChartApi; __barCount?: number }
}

/** Record every centred text the time axis's label canvas actually paints. */
async function recordAxisLabels(page: Page) {
  await page.addInitScript(() => {
    window.__axisLabels = [];
    const paint = CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillText = function (text, x, y, maxWidth) {
      const cell = this.canvas.closest('td');
      const row = cell?.parentElement as HTMLTableRowElement | null;
      const table = row?.closest('table');
      const isAxisLabels = !!table && row === table.rows[table.rows.length - 1]
        && cell === row.cells[1] && cell.querySelector('canvas') === this.canvas;
      if (isAxisLabels && this.textAlign === 'center') {
        const half = this.measureText(text).width / 2;
        window.__axisLabels!.push({
          text, left: x - half, right: x + half, axis: this.canvas.width / (this.getTransform().a || 1),
        });
      }
      if (maxWidth === undefined) paint.call(this, text, x, y);
      else paint.call(this, text, x, y, maxWidth);
    };
  });
}

/** Sweep the visible range across the sample in fractional-bar steps; return every label drawn. */
async function sweep(page: Page): Promise<Drawn[]> {
  return page.evaluate(async () => {
    const chart = window.__chart!;
    const bars = window.__barCount!;
    const ts = chart.timeScale();
    const frame = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    for (const span of [40, 120, 390]) {
      for (let from = 0; from + span < bars; from += span / 6 + 0.37) {
        ts.setVisibleLogicalRange({ from, to: from + span });
        await frame();
      }
    }
    return window.__axisLabels!;
  });
}

for (const dpr of DPRS) {
  test.describe(`chart time axis at DPR ${dpr}`, () => {
    test.use({ deviceScaleFactor: dpr });

    for (const width of WIDTHS) {
      test(`every time label draws whole (${width} px pane)`, async ({ page }) => {
        await recordAxisLabels(page);
        await page.setViewportSize({ width: 1000, height: 600 });
        await page.goto(`/e2e/fixtures/chart-time-axis.html?w=${width}`);
        await page.waitForFunction(() => !!window.__chart && (window.__axisLabels?.length ?? 0) > 0);
        const drawn = await sweep(page);
        const cut = drawn.filter((d) => d.left < -0.5 || d.right > d.axis + 0.5);
        expect(cut.slice(0, 5), `${cut.length} of ${drawn.length} labels cut at the edge`).toEqual([]);
        // Labels still draw: the year, the day and the clock all appear somewhere.
        const texts = new Set(drawn.map((d) => d.text));
        expect([...texts].some((t) => t === '2026')).toBe(true);
        expect([...texts].some((t) => /^\d{1,2} (Dec|Jan)$/.test(t))).toBe(true);
        expect([...texts].some((t) => /^\d{1,2}:\d{2} (AM|PM)$/.test(t))).toBe(true);
      });
    }
  });
}
