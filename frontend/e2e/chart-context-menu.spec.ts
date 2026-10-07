import { test, expect, type Page } from '@playwright/test';
import { CHART_CONTEXT_MENU_TICKET_WAIT_REASON } from '../src/chart/chartContextMenuConstants';
import { attachErrorCollector } from './helpers/errorCollector';
import { mockLiveTraderApi } from './helpers/liveTraderApi';

const ARTIFACTS = '/opt/cursor/artifacts';

/**
 * The menu prices its rows off the chart's price scale, so the chart needs
 * served candles. The sample desk refuses every backend read in the page
 * (sampleNetworkGate.ts), so the Trader opens on the live route with the API
 * mocked, holding SMPL 200 long like the sample account did.
 */
async function openTrader(page: Page) {
  const api = await mockLiveTraderApi(page);
  await page.goto('/?view=stock&symbol=SMPL');
  // First paint of the Trader chunk; same allowance as open-closed-orders.spec.ts.
  await expect(page.getByTestId('chart-desk-toolbar')).toBeVisible({ timeout: 20_000 });
  const chart = page.locator('.chart-body').first();
  await expect(chart).toBeVisible();
  await expect(page.locator('[data-testid^="ticker-chart-"]').first()).toHaveAttribute(
    'data-bar-count',
    /[1-9]/,
  );
  // The menu stages the already-mounted ticket (ibkr/orderTicketPrefill.ts);
  // the rail mounts it once the quote has loaded, and until then the priced
  // rows are locked with a reason (#566, covered by its own case below).
  await expect(page.locator('form.manual-order-ticket').first()).toBeVisible();
  return { chart, api };
}

/**
 * Right-click inside the plot area, away from the position tag. The plot is the first pane of
 * lightweight-charts (its table's first row, between the price axes). The spot 40% across and 60% down
 * the chart body is taken whenever the plot shows there. Where the position tag sits follows the price
 * scale, and on a short pane that spot can fall on the time axis under the tag, which opens the position
 * menu instead. So the first point of the plot itself that nothing covers is taken.
 */
async function rightClickChart(page: Page, chart = page.locator('.chart-body').first()) {
  const box = await chart.boundingBox();
  expect(box).toBeTruthy();
  if (!box) throw new Error('chart body has no box');
  const at = await chart.evaluate((body) => {
    const plot = body.querySelector('.tv-lightweight-charts table tr')?.children[1];
    if (!plot) return null;
    const shows = (x: number, y: number) => {
      const hit = document.elementFromPoint(x, y);
      return hit instanceof HTMLCanvasElement && plot.contains(hit);
    };
    const b = body.getBoundingClientRect();
    const usual = { x: b.x + b.width * 0.4, y: b.y + b.height * 0.6 };
    if (shows(usual.x, usual.y)) return usual;
    const p = plot.getBoundingClientRect();
    for (const fy of [0.5, 0.25, 0.75]) {
      for (const fx of [0.4, 0.25, 0.1, 0.55, 0.7, 0.85]) {
        const point = { x: p.x + p.width * fx, y: p.y + p.height * fy };
        if (shows(point.x, point.y)) return point;
      }
    }
    return null;
  });
  if (!at) throw new Error('no point of the plot is free of the position tag');
  await page.mouse.click(at.x, at.y, { button: 'right' });
  return box;
}

/** The chart column, its grid and each pane's chart body, as heights in px to a tenth. */
async function chartLayout(page: Page) {
  return page.locator('.stock-view-charts').evaluate((column) => {
    const height = (el: Element | null) =>
      Math.round((el?.getBoundingClientRect().height ?? 0) * 10) / 10;
    const panes: Record<string, number> = {};
    for (const cell of column.querySelectorAll('[data-testid^="chart-grid-cell-"]')) {
      panes[cell.getAttribute('data-testid') ?? ''] = height(cell.querySelector('.chart-body'));
    }
    return {
      column: height(column),
      grid: height(column.querySelector('[data-testid="chart-grid"]')),
      panes,
    };
  });
}

test.describe('Trader chart right-click context menu', () => {
  test('opens at the cursor with Webull rows priced off the chart', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openTrader(page);
    await rightClickChart(page);

    const menu = page.getByTestId('chart-context-menu');
    await expect(menu).toBeVisible();
    await expect(page.getByTestId('chart-context-menu-create_order')).toHaveText(
      /^Create New Order @\d+\.\d{2}$/,
    );
    await expect(page.getByTestId('chart-context-menu-buy')).toHaveText(
      /^Buy SMPL \d+ @\d+\.\d{2}$/,
    );
    await expect(page.getByTestId('chart-context-menu-sell')).toHaveText(
      /^Sell SMPL \d+ @\d+\.\d{2}$/,
    );
    // The mocked account holds SMPL 200 -- the flatten row is the shared SSOT button.
    await expect(page.getByTestId('chart-context-menu-close-position')).toHaveText(
      'Close Position',
    );
    await expect(page.getByTestId('chart-context-menu-view_details')).toHaveText(
      'View Trade Details',
    );
    await expect(page.getByTestId('chart-context-menu-show_layers')).toBeVisible();
    await expect(page.getByTestId('chart-context-menu-create_alert')).toBeDisabled();
    // The operator's watch list is a real action now (watch_list/), not a disabled stub.
    await expect(page.getByTestId('chart-context-menu-watch_list_add')).toHaveText(
      'Add to watch list',
    );
    await expect(page.getByTestId('chart-context-menu-watch_list_add')).toBeEnabled();
    await expect(page.getByTestId('chart-context-menu-reset')).toBeVisible();
    await expect(page.getByTestId('chart-context-menu-snapshot')).toBeVisible();
    await expect(page.getByTestId('chart-context-menu-hint')).toContainText(
      'trade ticket',
    );
    await page.screenshot({
      path: `${ARTIFACTS}/chart-context-menu-open.png`,
      fullPage: true,
    });

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Escape and click-outside dismiss it', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openTrader(page);

    await rightClickChart(page);
    await expect(page.getByTestId('chart-context-menu')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);

    await rightClickChart(page);
    await expect(page.getByTestId('chart-context-menu')).toBeVisible();
    await page.getByTestId('chart-desk-toolbar').click({ position: { x: 2, y: 2 } });
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Buy stages the trade ticket instead of placing an order', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const { api } = await openTrader(page);
    await rightClickChart(page);

    const buy = page.getByTestId('chart-context-menu-buy');
    const label = (await buy.textContent()) ?? '';
    const price = label.split('@')[1]?.trim();
    expect(price, `no price in "${label}"`).toMatch(/^\d+\.\d{2}$/);
    await buy.click();
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);

    const ticket = page.locator('form.manual-order-ticket').first();
    await expect(ticket).toBeVisible();
    await expect(
      ticket.locator('.manual-order-side button', { hasText: 'Buy' }),
    ).toHaveAttribute('aria-pressed', 'true');
    await expect(ticket.locator('#manual-order-limit')).toHaveValue(price!);
    await page.screenshot({
      path: `${ARTIFACTS}/chart-context-menu-buy-staged.png`,
      fullPage: true,
    });

    expect(api.mutations, 'staging must not send an order').toEqual([]);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Sell stages a SELL ticket at the same price', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openTrader(page);
    await rightClickChart(page);

    const sell = page.getByTestId('chart-context-menu-sell');
    const price = ((await sell.textContent()) ?? '').split('@')[1]?.trim();
    await sell.click();

    const ticket = page.locator('form.manual-order-ticket').first();
    await expect(
      ticket.locator('.manual-order-side button', { hasText: 'Sell' }),
    ).toHaveAttribute('aria-pressed', 'true');
    await expect(ticket.locator('#manual-order-limit')).toHaveValue(price!);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('priced rows say why until the quote brings the ticket (#566)', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const api = await mockLiveTraderApi(page);
    // Hold the quote: the rail mounts the ticket only once it has loaded. The ticker socket opens and
    // says nothing, as on a desk whose backend is slow to answer, so the note reads "Loading quote".
    // Unrouted, the socket has no server behind it: it fails at no fixed moment, and the note turns to
    // "No quote data".
    let releaseQuote: () => void = () => {};
    const quoteHeld = new Promise<void>((resolve) => {
      releaseQuote = resolve;
    });
    await page.routeWebSocket(/\/ws\/ticker\/SMPL(\?.*)?$/, () => {});
    await page.route('**/api/ticker/SMPL', async (route) => {
      await quoteHeld;
      await route.fallback();
    });
    await page.goto('/?view=stock&symbol=SMPL');
    await expect(page.getByTestId('chart-desk-toolbar')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('[data-testid^="ticker-chart-"]').first()).toHaveAttribute(
      'data-bar-count',
      /[1-9]/,
    );
    await expect(page.getByTestId('stock-view-rail-pending')).toBeVisible();
    await expect(page.locator('form.manual-order-ticket')).toHaveCount(0);
    // The wait lies over the charts and takes no room: the grid fills its column from the first paint.
    const note = page.getByTestId('stock-view-quote-overlay');
    await expect(note).toHaveText('Loading quote for SMPL…');
    await expect(note).toHaveAttribute('aria-live', 'polite');
    const waiting = await chartLayout(page);
    expect(waiting.grid, 'the chart grid fills its column while the quote loads').toBe(
      waiting.column,
    );

    await rightClickChart(page);
    for (const id of ['create_order', 'buy', 'sell']) {
      const row = page.getByTestId(`chart-context-menu-${id}`);
      await expect(row).toBeDisabled();
      await expect(row).toHaveAttribute('data-why', CHART_CONTEXT_MENU_TICKET_WAIT_REASON);
    }
    await expect(page.getByTestId('chart-context-menu-buy')).toHaveText(
      /^Buy SMPL \d+ @\d+\.\d{2}$/,
    );
    await expect(page.getByTestId('chart-context-menu-hint')).toHaveText(
      CHART_CONTEXT_MENU_TICKET_WAIT_REASON,
    );
    // A press on a locked row is refused out loud (ux/whyTip.ts), not dropped.
    await page.getByTestId('chart-context-menu-buy').click({ force: true });
    await expect(page.locator('#nova-why-tip')).toHaveText(CHART_CONTEXT_MENU_TICKET_WAIT_REASON);
    await expect(page.getByTestId('chart-context-menu')).toBeVisible();
    await page.screenshot({
      path: `${ARTIFACTS}/chart-context-menu-waiting-for-ticket.png`,
      fullPage: true,
    });

    // The quote lands, the ticket mounts, and the open menu unlocks in place.
    releaseQuote();
    const ticket = page.locator('form.manual-order-ticket').first();
    await expect(ticket).toBeVisible();
    await expect(note).toHaveCount(0);
    // Nothing jumps when the quote lands: every pane keeps the height it had while the quote loaded.
    expect(await chartLayout(page), 'the chart panes keep their size when the quote lands').toEqual(
      waiting,
    );
    const sell = page.getByTestId('chart-context-menu-sell');
    await expect(sell).toBeEnabled();
    await expect(page.getByTestId('chart-context-menu-hint')).toContainText('trade ticket');
    const price = ((await sell.textContent()) ?? '').split('@')[1]?.trim();
    expect(price, 'no price on the Sell row').toMatch(/^\d+\.\d{2}$/);
    await sell.click();
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);
    await expect(
      ticket.locator('.manual-order-side button', { hasText: 'Sell' }),
    ).toHaveAttribute('aria-pressed', 'true');
    await expect(ticket.locator('#manual-order-limit')).toHaveValue(price!);

    expect(api.mutations, 'staging must not send an order').toEqual([]);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Drawings submenu arms an existing draw tool', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const { chart } = await openTrader(page);
    await rightClickChart(page, chart);

    await page.getByTestId('chart-context-menu-drawings').click();
    const submenu = page.getByTestId('chart-context-menu-drawings-submenu');
    await expect(submenu).toBeVisible();
    await page.screenshot({
      path: `${ARTIFACTS}/chart-context-menu-drawings.png`,
      fullPage: true,
    });

    await page.getByTestId('chart-context-menu-tool-HorizontalLine').click();
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);
    await expect(chart).toHaveAttribute('data-active-draw-tool', 'HorizontalLine');

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('right-click on the Long/Short tag keeps the position menu', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openTrader(page);

    await page.getByTestId('chart-position-tag-btn').first().click({ button: 'right' });
    await expect(page.getByTestId('chart-position-menu')).toBeVisible();
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('still opens while the pane is in header fullscreen (#117)', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openTrader(page);

    const cell = page.getByTestId('chart-grid-cell-5Min');
    await cell.getByTestId('chart-expand-btn').click();
    await expect
      .poll(async () => page.evaluate(() => document.fullscreenElement !== null))
      .toBe(true);

    // A document.body portal would be invisible here -- only the fullscreen
    // element's subtree paints.
    await rightClickChart(page, cell.locator('.chart-body'));
    const menu = page.getByTestId('chart-context-menu');
    await expect(menu).toBeVisible();
    expect(
      await menu.evaluate((node) => document.fullscreenElement?.contains(node) ?? false),
    ).toBe(true);
    await page.screenshot({
      path: `${ARTIFACTS}/chart-context-menu-fullscreen.png`,
      fullPage: true,
    });

    await page.keyboard.press('Escape');
    await expect(menu).toHaveCount(0);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Show Layers toggles the same indicator SSOT as the desk toolbar', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openTrader(page);
    await rightClickChart(page);

    await page.getByTestId('chart-context-menu-show_layers').click();
    const vwap = page.getByTestId('chart-context-menu-layer-vwap');
    await expect(vwap).toBeVisible();
    const before = await vwap.getAttribute('aria-checked');
    await vwap.click();
    await expect(page.getByTestId('chart-context-menu')).toBeVisible();
    await expect(vwap).toHaveAttribute('aria-checked', before === 'true' ? 'false' : 'true');
    await page.screenshot({
      path: `${ARTIFACTS}/chart-context-menu-layers.png`,
      fullPage: true,
    });

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('View Trade Details docks Positions through the same event as the tag', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openTrader(page);
    await rightClickChart(page);
    await page.getByTestId('chart-context-menu-view_details').click();
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);
    await expect(page.getByTestId('stock-view-positions')).toBeVisible();

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('does not break double-click pane maximize', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const { chart } = await openTrader(page);
    await rightClickChart(page, chart);
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);

    const box = await chart.boundingBox();
    if (!box) throw new Error('chart body has no box');
    await page.mouse.dblclick(box.x + box.width * 0.5, box.y + box.height * 0.5);
    await expect(page.locator('.chart-grid--pane-maximized')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('.chart-grid--pane-maximized')).toHaveCount(0);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
