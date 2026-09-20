import { expect, test } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

test('measure the replay desk with populated tape and two snapshot consumers', async ({ page }) => {
  test.skip(!process.env.REPLAY_MEASURE_LABEL, 'Opt-in 60-second benchmark: set REPLAY_MEASURE_LABEL');
  test.setTimeout(150_000);
  const label = process.env.REPLAY_MEASURE_LABEL ?? 'after';
  const output = resolve(import.meta.dirname, '../../.tmp/replay-audit');
  mkdirSync(output, { recursive: true });
  const errors: string[] = [];
  const counts: Record<string, number> = {};
  let minute = 165;
  let activeJob = true;
  const start = Date.parse('2026-09-18T08:00:00Z') / 1000;
  const selection = { symbol: 'IMCC', date: '2026-09-18', start: '04:00', end: '09:30',
    start_ts: start, end_ts: start + 19800, coverage_through: start + 19800, trade_count: 250000, download_status: 'complete' };
  const prints = Array.from({length: 200}, (_, i) => ({
    time: new Date((start + minute * 60 - i) * 1000).toISOString(), price: 10 + (i % 20) / 100,
    size: 100, exchange: 'NASDAQ', unreported: i % 5 === 0,
  }));
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  await page.route('http://127.0.0.1:8999/**', async route => {
    const path = new URL(route.request().url()).pathname;
    counts[path] = (counts[path] ?? 0) + 1;
    let body: unknown = {};
    if (path === '/api/ibkr/status') body = { mode: 'sim', connected: true, enabled: true };
    if (path === '/api/sim/clock') {
      if (route.request().method() === 'POST') minute = route.request().postDataJSON().minute_from_open ?? minute;
      body = { sim: true, paused: true, phase: 'premarket', minute_from_open: minute, minute_max: 330,
        session_date: '2026-09-18', session_open_et: '2026-09-18T04:00:00-04:00',
        session_close_et: '2026-09-18T09:30:00-04:00', replay_source: 'historical', replay_symbol: 'IMCC',
        replay_date: '2026-09-18', sim_time_et: new Date((start + minute * 60) * 1000).toISOString() };
    }
    if (path === '/api/capture/sessions') body = { days: [], tickers_by_day: {} };
    if (path === '/api/sim/history') body = { selection, default_date: '2026-09-18', jobs: [{
      ...selection, id: 'sample', kind: 'trades', status: activeJob ? 'running' : 'complete', count: 125000, pages: 125,
      cursor: start + (activeJob ? 9900 : 19800), progress_pct: activeJob ? 50 : 100, downloaded_through: start + (activeJob ? 9900 : 19800), eta_seconds: activeJob ? 1500 : null,
      age_seconds: 3, stale: false, started: Date.now()/1000 - 1500, updated: Date.now()/1000 - 3, error: null,
    }] };
    if (path.startsWith('/api/sim/history/snapshot/')) body = { active: true, symbol: 'IMCC', selection,
      source: 'trades', as_of: new Date((start+minute*60)*1000).toISOString(), last: minute === 0 ? null : 10.19, volume: minute === 0 ? 0 : 20000000,
      open: minute === 0 ? null : 10, high: minute === 0 ? null : 10.2, low: minute === 0 ? null : 9.8, prev_close: 9.9, bid: null, ask: null, depth_available: false,
      prints: minute === 0 ? [] : prints.map((p,i) => ({...p,ordinal: minute*1000-i,time: new Date((start+minute*60-i/1000)*1000).toISOString()})) };
    if (path === '/api/sim/history/select') body = selection;
    await route.fulfill({json: body});
  });
  await page.goto('/e2e/fixtures/replay-desk.html');
  await expect(page.getByTestId('replay-count')).toHaveText('200', {timeout: 20000});
  await page.screenshot({path: resolve(output, `${label}-01-desk-dark.png`), fullPage: true});
  await page.getByText('Historical replay', {exact: true}).click();
  await page.screenshot({path: resolve(output, `${label}-02-panel-dark.png`), fullPage: true});
  await page.keyboard.press('Escape');
  // Baseline details does not implement Escape; close explicitly for the idle interval.
  const details = page.locator('details[open]');
  if (await details.count()) await details.locator('summary').click();
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));
  await page.getByText('Historical replay', {exact: true}).click();
  await page.screenshot({path: resolve(output, `${label}-03-panel-light.png`), fullPage: true});
  await page.keyboard.press('Escape');
  if (await details.count()) await details.locator('summary').click();
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Performance.enable');
  const geometry = () => page.evaluate(() => {
    const tape = document.querySelector('.ts-panel__rows');
    return {rows: document.querySelectorAll('.ts-row').length, nodes: document.querySelectorAll('*').length,
      viewport: tape?.clientHeight ?? null, scrollHeight: tape?.scrollHeight ?? null,
      documentHeight: document.documentElement.scrollHeight};
  });
  const beforeGeometry = await geometry();
  const beforeMetrics = await cdp.send('Performance.getMetrics');
  const idleCounts = {...counts};
  const idle = await page.evaluate(async () => {
    const frames: number[] = [], tasks: number[] = [];
    let previous = performance.now(), active = true;
    const observer = new PerformanceObserver(list => tasks.push(...list.getEntries().map(e => e.duration)));
    observer.observe({entryTypes: ['longtask']});
    const frame = (now: number) => { frames.push(now-previous); previous=now; if(active) requestAnimationFrame(frame); };
    requestAnimationFrame(frame);
    await new Promise(r => setTimeout(r, 60000));
    active=false; observer.disconnect();
    return {frames: frames.length, meanFps: frames.length/60, delayedFrames: frames.filter(n=>n>34).length,
      longTasks: tasks.length, totalBlockingMs: tasks.reduce((sum,n)=>sum+Math.max(0,n-50),0)};
  });
  const requests = Object.fromEntries(Object.entries(counts).map(([k,v])=>[k,v-(idleCounts[k]??0)]));
  const afterMetrics = await cdp.send('Performance.getMetrics');
  activeJob = false;
  await expect(page.locator('.sim-history__summary')).toContainText('complete');
  const idleStart = counts['/api/sim/history'];
  await page.waitForTimeout(11000);
  const idleHistoryRequests11s = counts['/api/sim/history'] - idleStart;
  expect(idleHistoryRequests11s).toBeLessThanOrEqual(3);
  const slider = page.getByTestId('sim-session-scrubber');
  await slider.focus(); await page.keyboard.press('Home');
  await expect(page.getByTestId('replay-count')).toHaveText('0');
  await page.screenshot({path: resolve(output, `${label}-04-rewind.png`), fullPage: true});
  await page.keyboard.press('ArrowRight');
  await expect(page.getByTestId('replay-count')).toHaveText('200');
  await page.screenshot({path: resolve(output, `${label}-05-early.png`), fullPage: true});
  await page.keyboard.press('End');
  await expect(slider).toHaveValue('330');
  await expect(page.locator('.ts-row').first()).toContainText('09:30:00');
  await expect(page.getByTestId('replay-count')).toHaveText('200');
  await page.screenshot({path: resolve(output, `${label}-06-late.png`), fullPage: true});
  const tape = page.locator('.ts-panel__rows');
  if (await tape.count()) await tape.evaluate(el => {el.scrollTop=el.scrollHeight; el.dispatchEvent(new Event('scroll'));});
  const afterGeometry = await geometry();
  const heap = (metrics: {metrics: {name: string; value: number}[]}) => metrics.metrics.find(x=>x.name==='JSHeapUsedSize')?.value;
  writeFileSync(resolve(output, `${label}-browser.json`), JSON.stringify({label, fixture:'production header + quote rail, 200 API prints, two snapshot consumers; routed API, not Gateway', idle, requests,
    beforeGeometry, afterGeometry, idleHistoryRequests11s, heapBefore: heap(beforeMetrics), heapAfter: heap(afterMetrics), errors}, null, 2));
  expect(errors).toEqual([]);
});
