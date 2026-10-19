/**
 * Screenshot the desk /review route. One Chromium stays up for the MCP process.
 * Stdin is one JSON object per line: {url, dest}. Stdout is one JSON answer per line.
 * `--once <url> <dest>` takes a single shot and exits (used for the PR pictures).
 */
import { createRequire } from 'node:module';
import { createInterface } from 'node:readline';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, '../frontend/package.json'));

function loadChromium() {
  try {
    return require('playwright').chromium;
  } catch {
    return require('playwright-core').chromium;
  }
}

function launchOptions() {
  const candidates = [process.env.NOVA_CHROME, '/usr/bin/google-chrome', '/usr/local/bin/google-chrome'].filter(Boolean);
  for (const executablePath of candidates) {
    if (existsSync(executablePath)) return { headless: true, executablePath };
  }
  return { headless: true };
}

async function shot(page, url, dest) {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForSelector('[data-review-ready="1"]', { timeout: 25000 });
  await page.screenshot({ path: dest, fullPage: false });
}

async function once(url, dest) {
  const browser = await loadChromium().launch(launchOptions());
  try {
    const page = await browser.newPage();
    await shot(page, url, dest);
  } finally {
    await browser.close();
  }
}

async function serve() {
  const browser = await loadChromium().launch(launchOptions());
  const page = await browser.newPage();
  process.stdout.write(`${JSON.stringify({ ok: true, ready: true })}\n`);
  const lines = createInterface({ input: process.stdin });
  for await (const line of lines) {
    if (!line.trim()) continue;
    let req;
    try {
      req = JSON.parse(line);
      await shot(page, req.url, req.dest);
      process.stdout.write(`${JSON.stringify({ ok: true, dest: req.dest })}\n`);
    } catch (err) {
      process.stdout.write(`${JSON.stringify({ ok: false, error: 'REVIEW_SHOT_FAILED', detail: String(err) })}\n`);
    }
  }
  await browser.close();
}

const args = process.argv.slice(2);
try {
  if (args[0] === '--once') {
    await once(args[1], args[2]);
  } else {
    await serve();
  }
} catch (err) {
  const missing = /Cannot find module/.test(String(err));
  process.stdout.write(`${JSON.stringify({
    ok: false,
    error: missing ? 'REVIEW_SHOT_UNAVAILABLE' : 'REVIEW_SHOT_FAILED',
    detail: String(err),
  })}\n`);
  process.exit(missing ? 2 : 1);
}
