/**
 * Bring an already-running Nova to a ticker. The second instance only focuses
 * and, when the launch URL asks, posts the same open the review page uses.
 * It does not place an order.
 */

const SYMBOL = /^[A-Z][A-Z0-9.\-]{0,9}$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;
const CLOCK = /^([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/;
const REVIEW_KEYS = new Set(['symbol', 'date', 'as_of', 'tf']);

export function readOpenRequest(argv) {
  const args = Array.isArray(argv) ? argv : [];
  const raw = args.find((item) => typeof item === 'string' && item.startsWith('nova://open'));
  if (!raw) return null;
  let url;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (url.protocol !== 'nova:' || url.hostname !== 'open') return null;
  const symbol = (url.searchParams.get('symbol') || '').toUpperCase();
  const date = url.searchParams.get('date') || '';
  const asOf = url.searchParams.get('as_of') || '';
  if (!SYMBOL.test(symbol) || !DAY.test(date)) return null;
  if (asOf && !CLOCK.test(asOf)) return null;
  return { symbol, date, asOf: asOf || null };
}

export function separateSimLocation(base, request) {
  const origin = String(base || 'http://127.0.0.1:5173').replace(/\/$/, '');
  const params = new URLSearchParams();
  params.set('symbol', request.symbol);
  params.set('date', request.date);
  const asOf = String(request.asOf || '').slice(0, 5);
  if (asOf) params.set('as_of', asOf);
  return `${origin}/review?${params.toString()}`;
}

export function reviewWindowUrl(raw, base) {
  const text = String(raw || '');
  if (!text.startsWith('/review?')) return null;
  const params = new URLSearchParams(text.slice('/review?'.length));
  if (!SYMBOL.test(params.get('symbol') || '') || !DAY.test(params.get('date') || '')) return null;
  const asOf = params.get('as_of');
  if (asOf && !/^\d{2}:\d{2}$/.test(asOf)) return null;
  for (const key of params.keys()) {
    if (!REVIEW_KEYS.has(key)) return null;
  }
  return `${String(base || 'http://127.0.0.1:5173').replace(/\/$/, '')}${text}`;
}

export function createSeparateSimWindow(BrowserWindow, location, options = {}) {
  const win = new BrowserWindow(options);
  win.loadURL(location);
  return win;
}

export async function deliverOpen(request, { apiBase, fetchImpl }) {
  const root = String(apiBase || 'http://127.0.0.1:8000').replace(/\/$/, '');
  const tokenRes = await fetchImpl(`${root}/api/agent/open-token`);
  if (!tokenRes.ok) {
    const error = new Error('Nova desk did not answer');
    error.code = 'DESK_NOT_RUNNING';
    throw error;
  }
  const tokenBody = await tokenRes.json();
  const payload = { symbol: request.symbol, date: request.date };
  if (request.asOf) payload.as_of = request.asOf;
  const response = await fetchImpl(`${root}/api/agent/open-in-nova`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Nova-Open-Token': tokenBody.token,
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(body?.detail?.error || body?.error || 'open failed');
    error.code = body?.detail?.reason || body?.reason || 'BAD_REQUEST';
    throw error;
  }
  return body;
}
