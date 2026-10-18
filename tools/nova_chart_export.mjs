/** Shared Nova native-canvas export and stage benchmark. No trading endpoint access. */
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const { chromium } = require('@playwright/test');
const args = process.argv.slice(2);
const option = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback;
const url = option('--url', 'http://127.0.0.1:5179/chart-gateway.html');
const apiUrl = option('--api-url', 'http://127.0.0.1:8009');
const output = path.resolve(option('--output', '.tmp/nova-chart-export'));
const samples = Number(option('--samples', '0'));
if (!Number.isInteger(samples) || samples < 0 || samples > 50) throw new Error('samples must be0..50');
const allowedOrigins = new Set([url, apiUrl].map(value => {
  const target = new URL(value);
  if (target.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(target.hostname)) throw new Error('Gateway must be local HTTP');
  return target.origin;
}));
await fs.mkdir(output, { recursive: false });
const errors = [], requests = [], blocked = [];
const started = performance.now();
const browser = await chromium.launch({ headless: true });
const launchMs = performance.now() - started;
try {
  const context = await browser.newContext({ viewport: { width: 3000, height: 1900 }, deviceScaleFactor: 1 });
  await context.route('**/*', async route => {
    const target = new URL(route.request().url());
    if (!allowedOrigins.has(target.origin)) {
      blocked.push(target.origin + target.pathname); await route.abort(); return;
    }
    requests.push({ method: route.request().method(), url: target.origin + target.pathname });
    await route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  const nav = performance.now();
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.novaCharts?.ready || window.novaCharts?.error, { timeout: 30000 });
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const firstReadyMs = performance.now() - nav;
  const state = await page.evaluate(() => ({ error: window.novaCharts.error, metrics: window.novaCharts.metrics,
    entries: window.novaCharts.entries.map(e => ({ id: e.id, symbol: e.symbol, date: e.date, as_of_m: e.as_of_m,
      bars_1m: e.bars_1m.length, bars_5m: e.bars_5m.length,
      ...(e.bar_seconds ? { bar_seconds: e.bar_seconds, bars_sub: e.bars_sub.length } : {}) })) }));
  if (state.error || errors.length) throw new Error(JSON.stringify({ state, errors }));
  const paneCount = state.entries.reduce((sum, e) => sum + (e.bar_seconds ? 1 : 2), 0);
  const overlays = await page.evaluate(() => [...document.querySelectorAll('[data-testid="causal-context-overlay"]')].map(node => {
    const canvas = node;
    const entry = window.novaCharts.entries.find(e => String(e.id) === node.dataset.entryId);
    const timeframe = node.dataset.timeframe;
    const five = timeframe === '5Min';
    const bars = timeframe === '1Min' ? entry.bars_1m : five ? entry.bars_5m : entry.bars_sub;
    const decision = entry.as_of_t ? Date.parse(entry.as_of_t) : null;
    const future = decision !== null && bars.some(bar => five ? Date.parse(bar.t) + 300000 > decision : Date.parse(bar.t) >= decision);
    const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    let amber = 0;
    for (let i = 0; i < pixels.length; i += 4) {
      if (Math.abs(pixels[i] - 242) < 8 && Math.abs(pixels[i+1] - 156) < 8 && Math.abs(pixels[i+2] - 82) < 8 && pixels[i+3] > 20) amber++;
    }
    return { symbol: entry.symbol, timeframe, future, amber_pixels: amber };
  }));
  if (overlays.length !== paneCount || overlays.some(o => o.future && o.amber_pixels === 0)) throw new Error('Visible future-context overlay missing');
  await page.screenshot({ path: path.join(output, 'NOVA_GATEWAY_VIEW.png'), fullPage: true });
  const save = async (file, index) => {
    const begin = performance.now();
    const result = await page.evaluate(i => window.novaCharts.exportPng(i), index);
    if (!result.data.startsWith('data:image/png;base64,')) throw new Error('Native export not PNG');
    await fs.writeFile(path.join(output, file), Buffer.from(result.data.split(',')[1], 'base64'), { flag: 'wx' });
    return { export_ms: result.export_ms, browser_to_disk_ms: performance.now() - begin };
  };
  const firstExport = await save('NOVA_HISTORICAL_OVERVIEW.png', undefined);
  console.log(JSON.stringify({ overview_ready: path.join(output, 'NOVA_HISTORICAL_OVERVIEW.png'), state, firstReadyMs, firstExport }));
  const details = [];
  for (const e of state.entries) {
    const safe = e.symbol.replace(/[^a-zA-Z0-9.-]/g, '_');
    const frames = e.bar_seconds ? `${e.bar_seconds}s` : '1m_5m';
    details.push({ ...e, ...await save(`${String(e.id + 1).padStart(2, '0')}_${safe}_${e.date}_${frames}.png`, e.id) });
  }
  const warm = await page.evaluate(n => {
    const result = [];
    for (let i = 0; i < n; i++) { const captured = window.novaCharts.exportPng(); result.push(captured.export_ms); }
    return result;
  }, samples);
  const fetchSamples = await page.evaluate(async ({ n, api }) => {
    const times = [];
    for (let i = 0; i < n; i++) {
      const start = performance.now();
      const response = await fetch(`${api}/api/agent/chart-gallery`);
      if (!response.ok) throw new Error(`HTTP${response.status}`);
      await response.json(); times.push(performance.now() - start);
    }
    return times;
  }, { n: samples, api: apiUrl });
  const stats = rows => { const sorted = [...rows].sort((a,b) => a-b); if (!sorted.length) return { n: 0, p50_ms: null, p95_ms: null, samples_ms: [] }; return { n: sorted.length,
    p50_ms: sorted[Math.max(0, Math.ceil(.5 * sorted.length) - 1)],
    p95_ms: sorted[Math.max(0, Math.ceil(.95 * sorted.length) - 1)], samples_ms: rows }; };
  const report = { created_utc: new Date().toISOString(), source: 'actual frozen selection via Nova chart gateway',
    browser_launch_ms: launchMs, first_navigation_to_ready_ms: firstReadyMs, first_observed: state.metrics,
    first_export: firstExport, warm_native_overview_export: stats(warm), warm_endpoint_fetch: stats(fetchSamples),
    details, visible_overlay_audit: overlays, errors, blocked_requests: blocked, requests, library_transfer: 'not included',
    caveat: 'Cold first-observed navigation includes modules/browser preparation; not a process-cold distribution. Warm export reuses initialized native charts; no end-to-end under1second claim.' };
  await fs.writeFile(path.join(output, 'CAPTURE_VERIFICATION.json'), JSON.stringify(report, null, 2), { flag: 'wx' });
  console.log(JSON.stringify({ complete: true, output, warm_native_overview_export: report.warm_native_overview_export,
    warm_endpoint_fetch: report.warm_endpoint_fetch, details: details.length, errors, blocked }));
} finally { await browser.close(); }
