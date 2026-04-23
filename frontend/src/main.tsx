import { StrictMode } from 'react';
import { isNovaApiDebug } from './debug';
import './index.css';

void bootstrap().catch((err) => {
  console.error(err);
  const el = document.getElementById('root');
  if (el) el.textContent = 'Failed to start the app. Check the console.';
});

async function bootstrap(): Promise<void> {
  const base = await resolveApiBase();
  window.__NOVA_API_BASE__ = base;
  if (isNovaApiDebug()) {
    console.info('[Nova] API base:', base, '| Try:', `${base}/api/health`);
  }

  const { createRoot } = await import('react-dom/client');
  const { default: App } = await import('./App.tsx');

  const rootEl = document.getElementById('root');
  if (!rootEl) {
    console.error('#root missing');
    return;
  }

  createRoot(rootEl).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

async function resolveApiBase(): Promise<string> {
  const raw = import.meta.env.VITE_API_BASE_URL;
  if (typeof raw === 'string' && raw.trim()) {
    const b = raw.replace(/\/$/, '');
    if (isNovaApiDebug()) console.info('[Nova] API base from Vite env:', b);
    return b;
  }
  try {
    const res = await fetch('/config.json', { cache: 'no-store' });
    if (res.ok) {
      const data = (await res.json()) as { apiBase?: string };
      const b = data.apiBase?.trim();
      if (b) {
        const out = b.replace(/\/$/, '');
        if (isNovaApiDebug()) console.info('[Nova] API base from /config.json:', out);
        return out;
      }
    } else if (isNovaApiDebug()) {
      console.warn('[Nova] /config.json HTTP', res.status, res.statusText);
    }
  } catch (e) {
    if (isNovaApiDebug()) console.warn('[Nova] /config.json fetch failed:', e);
  }
  if (isNovaApiDebug()) {
    console.warn('[Nova] API base falling back to http://localhost:8000');
  }
  return 'http://localhost:8000';
}
