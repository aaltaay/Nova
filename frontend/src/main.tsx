import { StrictMode } from 'react';
import { isNovaApiDebug } from './debug';
import { initThemeFromStorage } from './theme/themePrefs';
import './index.css';

initThemeFromStorage();

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

  installGlobalErrorReporting();
}

function installGlobalErrorReporting(): void {
  window.addEventListener('error', (ev) => {
    const msg = ev.message || String(ev.error ?? 'window.error');
    const stack = ev.error instanceof Error ? ev.error.stack : undefined;
    void import('./utils/reportClientError').then(({ reportClientError }) => {
      reportClientError({ message: msg, stack, source: 'window.onerror' });
    });
  });
  window.addEventListener('unhandledrejection', (ev) => {
    const reason = ev.reason;
    const msg =
      reason instanceof Error
        ? reason.message
        : typeof reason === 'string'
          ? reason
          : 'unhandledrejection';
    const stack = reason instanceof Error ? reason.stack : undefined;
    void import('./utils/reportClientError').then(({ reportClientError }) => {
      reportClientError({ message: msg, stack, source: 'unhandledrejection' });
    });
  });
}

function readApiBaseFromMeta(): string | null {
  if (typeof document === 'undefined') return null;
  const el = document.querySelector('meta[name="nova-api-base"]');
  const v = el?.getAttribute('content')?.trim();
  if (v && v.startsWith('http')) return v.replace(/\/$/, '');
  return null;
}

async function resolveApiBase(): Promise<string> {
  const fromDesktop = window.novaDesktop?.apiBase?.trim();
  if (fromDesktop && fromDesktop.startsWith('http')) {
    if (isNovaApiDebug()) console.info('[Nova] API base from Electron:', fromDesktop);
    return fromDesktop.replace(/\/$/, '');
  }

  const fromMeta = readApiBaseFromMeta();
  if (fromMeta) {
    if (isNovaApiDebug()) console.info('[Nova] API base from index.html meta:', fromMeta);
    return fromMeta;
  }

  const raw = import.meta.env.VITE_API_BASE_URL;
  if (typeof raw === 'string' && raw.trim()) {
    const b = raw.replace(/\/$/, '');
    if (isNovaApiDebug()) console.info('[Nova] API base from Vite env:', b);
    return b;
  }
  try {
    const res = await fetch('/config.json', { cache: 'no-store' });
    const ct = (res.headers.get('content-type') || '').toLowerCase();
    if (!res.ok) {
      if (isNovaApiDebug()) console.warn('[Nova] /config.json HTTP', res.status);
    } else {
      const text = await res.text();
      const looksJson = text.trimStart().startsWith('{');
      if (ct.includes('application/json') && looksJson) {
        const data = JSON.parse(text) as { apiBase?: string };
        const b = data.apiBase?.trim();
        if (b && b.startsWith('http')) {
          const out = b.replace(/\/$/, '');
          if (isNovaApiDebug()) console.info('[Nova] API base from /config.json:', out);
          return out;
        }
      } else if (isNovaApiDebug()) {
        console.warn(
          '[Nova] /config.json is not real JSON (often SPA fallback HTML).',
          'content-type:',
          ct,
          'Redeploy frontend with VITE_API_BASE_URL at build time, or use meta injection.',
        );
      }
    }
  } catch (e) {
    if (isNovaApiDebug()) console.warn('[Nova] /config.json fetch failed:', e);
  }
  if (isNovaApiDebug()) {
    console.warn('[Nova] API base falling back to http://127.0.0.1:8000');
  }
  return 'http://127.0.0.1:8000';
}
