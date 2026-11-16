/**
 * Start the browser reload hold in this window (#612): wire the dev server's
 * hot channel and render the pending-code notice in its own root, outside the
 * desk's tree, so every page -- the desk, a Stock View pop-out, the Top 9
 * pop-up, the review page -- gets it without the app shell knowing. main.tsx
 * loads this only when `import.meta.env.DEV`; builds drop it.
 */
import { createRoot } from 'react-dom/client';
import { installReloadHold, type HotChannel } from './installReloadHold';
import { PendingCodeNotice } from './PendingCodeNotice';

const HOST_ID = 'nova-dev-reload-hold';

async function fetchPage(): Promise<string> {
  const res = await fetch(import.meta.env.BASE_URL || '/', { cache: 'no-store' });
  if (!res.ok) throw new Error(`dev server answered ${res.status}`);
  return res.text();
}

export function startReloadHold(win: Window): void {
  const doc = win.document;
  const store = installReloadHold({
    doc,
    hot: import.meta.hot as unknown as HotChannel | undefined,
    fetchPage,
  });
  if (!store || doc.getElementById(HOST_ID)) return;
  const host = doc.createElement('div');
  host.id = HOST_ID;
  doc.body.appendChild(host);
  createRoot(host).render(<PendingCodeNotice store={store} reload={() => win.location.reload()} />);
}
