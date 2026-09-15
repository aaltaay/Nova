import { API_URL, WS_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import type { AdviseEstimate, AdviseRun } from './types';

export async function fetchAdviseEstimate(
  symbol: string,
  depth: number,
): Promise<AdviseEstimate> {
  const res = await novaFetch(
    `${API_URL}/advise/estimate?symbol=${encodeURIComponent(symbol)}&depth=${depth}`,
  );
  if (!res.ok) throw new Error(await _detail(res));
  return res.json();
}

export async function fetchAdviseLatest(
  symbol: string,
  depth: number,
): Promise<AdviseRun | null> {
  const res = await novaFetch(
    `${API_URL}/advise/latest?symbol=${encodeURIComponent(symbol)}&depth=${depth}`,
  );
  if (!res.ok) throw new Error(await _detail(res));
  const body = await res.json();
  return body.run ?? null;
}

export async function fetchAdviseHistory(symbol: string): Promise<AdviseRun[]> {
  const res = await novaFetch(
    `${API_URL}/advise/history?symbol=${encodeURIComponent(symbol)}`,
  );
  if (!res.ok) throw new Error(await _detail(res));
  const body = await res.json();
  return body.runs ?? [];
}

export async function fetchAdviseRun(runId: number): Promise<AdviseRun> {
  const res = await novaFetch(`${API_URL}/advise/runs/${runId}`);
  if (!res.ok) throw new Error(await _detail(res));
  return res.json();
}

export async function postAdviseRun(
  symbol: string,
  depth: number,
  forceRefresh: boolean,
): Promise<AdviseRun> {
  const res = await novaFetch(`${API_URL}/advise/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      symbol,
      depth,
      force_refresh: forceRefresh,
    }),
  });
  if (!res.ok) throw new Error(await _detail(res));
  return res.json();
}

export async function postAdviseCancel(runId: number): Promise<AdviseRun> {
  const res = await novaFetch(`${API_URL}/advise/runs/${runId}/cancel`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(await _detail(res));
  return res.json();
}

export async function postAdviseRetry(runId: number): Promise<AdviseRun> {
  const res = await novaFetch(`${API_URL}/advise/runs/${runId}/retry`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(await _detail(res));
  return res.json();
}

export function adviseWsUrl(runId: number): string {
  return `${WS_BASE_URL}/ws/advise/${runId}`;
}

async function _detail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === 'string') return body.detail;
  } catch {
    /* use status text */
  }
  return res.statusText || `HTTP ${res.status}`;
}
