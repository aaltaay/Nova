/**
 * Turn a page into the public demo (ADR 043). Called from main.tsx before anything else when the
 * build is the demo build; a normal build never loads this module.
 */
import { NOW_MS } from './data/market';
import { installDemoClock } from './demoClock';
import { demoMisses, installDemoTransport } from './demoTransport';

/** First-visit layout: the plan open, past setups and levels on the 1-minute chart, five HOD rows. */
const SEEDS: Record<string, string> = {
  'nova.stockRead.layers': JSON.stringify({
    schema_version: 1,
    value: { setups: true, levels: true, past: true, labels: 'compact', hidden: [], plan: 'open' },
  }),
  'nova.hodMomo.strip.v1': JSON.stringify({ schema_version: 1, rows: 5, folded: false }),
  'nova.stockView.openOrders.sampleHidden': '1',
};

/**
 * The screen-recording chip speaks for the desktop app, and the demo records nothing; the Bots
 * page's source note speaks to the operator about their own material. Neither belongs on a public page.
 */
const DEMO_CSS = '[data-testid="screen-rec-chip"], .bots-source { display: none !important; }';

function seedStorage(win: Window): void {
  try {
    const storage = win.localStorage;
    for (const [key, value] of Object.entries(SEEDS)) {
      if (storage.getItem(key) === null) storage.setItem(key, value);
    }
  } catch {
    // Storage refused (a private window): the desk starts with its own defaults.
  }
}

export function installDemo(win: Window & typeof globalThis): void {
  installDemoClock(NOW_MS, win);
  installDemoTransport(win);
  seedStorage(win);
  // What the demo had no answer for, for whoever finds a blank panel: `__novaDemo.misses` in the console.
  Object.defineProperty(win, '__novaDemo', { value: { misses: demoMisses } });
  const style = win.document.createElement('style');
  style.dataset.novaDemo = '1';
  style.textContent = DEMO_CSS;
  win.document.head.appendChild(style);
}
