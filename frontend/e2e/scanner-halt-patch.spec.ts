import { test, expect } from '@playwright/test';
import type { Page, WebSocketRoute } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

type HaltState = boolean | null;

async function replayScanner(page: Page, pendingHalted?: boolean) {
  let current: { socket: WebSocketRoute; ready: boolean } | undefined;
  let liveReads = 0;
  let pending = false;
  let release!: () => void;
  const pendingBody = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    const historical = path.startsWith('/api/history/');
    if (path === '/api/gappers') {
      liveReads += 1;
      if (liveReads === 2 && pendingHalted !== undefined) {
        pending = true;
        await pendingBody;
      }
    }
    const halted = !historical && liveReads >= 2 && pendingHalted !== undefined ? pendingHalted : false;
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({
      dates: ['2026-09-23'], gappers: [{ symbol: 'PFSA', price: historical ? 4.2 : 4.3, halted }],
      gainers: [], losers: [], afterhours: [], large_cap: [], catalysts: [], table_state: 'frozen', last_scan: 100,
    }) });
  });
  await page.routeWebSocket('**/ws/scanner', socket => {
    const session = { socket, ready: false };
    current = session;
    socket.onMessage(message => {
      if (JSON.parse(message.toString()).type === 'set_active_tab') session.ready = true;
    });
  });
  return {
    async socket(previous?: WebSocketRoute) {
      // A retired route survives in the test; the new client's handshake proves readiness.
      await expect.poll(() => Boolean(current?.ready && current.socket !== previous)).toBe(true);
      return current!.socket;
    },
    async pendingRead() { await expect.poll(() => pending).toBe(true); },
    release,
  };
}

function haltPatch(socket: WebSocketRoute, halted: HaltState, ts: number) {
  socket.send(JSON.stringify({ type: 'halt_patch', rows: [{ symbol: 'PFSA', halted }], ts }));
}

// Socket and API are replayed browser facts; this never opens a real IB line.
test('a frozen row follows halt/resume/unknown while history keeps its own halt evidence', async ({ page }) => {
  const { errors } = attachErrorCollector(page);
  const replay = await replayScanner(page);
  await page.goto('/e2e/fixtures/scannerHalt.html');
  const row = page.getByTestId('row-PFSA');
  await expect(row).toContainText('4.3 · TRADING');
  const scannerSocket = await replay.socket();
  await page.getByTestId('halted-chip').click();
  await expect(row).toHaveCount(0);
  haltPatch(scannerSocket, true, 200);
  await expect(row).toContainText('4.3 · HALTED');
  await expect(page.getByTestId('quote-age')).toHaveText('100');
  haltPatch(scannerSocket, null, 201);
  await expect(row).toContainText('UNKNOWN');
  haltPatch(scannerSocket, false, 202);
  await expect(row).toHaveCount(0);
  await page.getByTestId('halted-chip').click();
  await page.getByTestId('history').click();
  await expect(page.getByTestId('history-date')).toHaveText('2026-09-23');
  await expect(row).toContainText('4.2 · TRADING');
  haltPatch(scannerSocket, true, 203);
  await expect(row).toContainText('4.2 · TRADING');
  await page.getByTestId('live').click();
  await expect(page.getByTestId('history-date')).toHaveText('Live');
  await expect(row).toContainText('4.3 · TRADING');
  const resumedSocket = await replay.socket(scannerSocket);
  haltPatch(resumedSocket, true, 204);
  await expect(row).toContainText('4.3 · HALTED');
  await expect(page.getByTestId('quote-age')).toHaveText('100');
  expect(errors).toEqual([]);
});

for (const receipt of [true, null, false] as const) {
  const state = receipt === true ? 'HALTED' : receipt === false ? 'TRADING' : 'UNKNOWN';
  test(`newer ${state} evidence survives a pending live snapshot without changing frozen quote age`, async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const baseline = receipt === false;
    const replay = await replayScanner(page, baseline);
    await page.goto('/e2e/fixtures/scannerHalt.html');
    const row = page.getByTestId('row-PFSA');
    const age = page.getByTestId('quote-age');
    await expect(row).toContainText('4.3 · TRADING');
    const previous = await replay.socket();
    await page.getByTestId('history').click();
    await expect(page.getByTestId('history-date')).toHaveText('2026-09-23');
    await expect(row).toContainText('4.2 · TRADING');
    await page.getByTestId('live').click();
    await expect(page.getByTestId('history-date')).toHaveText('Live');
    await replay.pendingRead();
    const socket = await replay.socket(previous);
    if (receipt === false) {
      haltPatch(socket, true, 299);
      await expect(row).toContainText('4.2 · HALTED');
    }
    haltPatch(socket, receipt, 300);
    await expect(row).toContainText(`4.2 · ${state}`);
    await expect(age).toHaveText('100');
    replay.release();
    await expect(row).toContainText(`4.3 · ${state}`);
    await expect(age).toHaveText('100');

    // Receipt protection belongs to the pending request; a later snapshot can change it.
    await page.getByTestId('refresh-live').click();
    await expect(row).toContainText(`4.3 · ${baseline ? 'HALTED' : 'TRADING'}`);
    await expect(age).toHaveText('100');
    expect(errors).toEqual([]);
  });
}
