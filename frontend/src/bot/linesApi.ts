/**
 * IBKR's three Level 2 lines and the lending switch (ADR 044), for the Bots page: `GET /api/ibkr/depth/lines`,
 * `PATCH /api/ibkr/depth/lending`. The view is read by the one parser lending owns (`ibkr/depthLines`); this
 * page adds its refusals in words -- a backend without the route, the key, a shape it does not read. The
 * switch changes who may take a line from a hidden Trader tab, so it carries the desk's API key and the sample
 * desk refuses it before any request.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { normalizeDepthLines, type DepthLinesView } from '../ibkr';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';

const obj = (v: unknown): Record<string, unknown> | null =>
  (v != null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null);

async function read(res: Response): Promise<DepthLinesView> {
  if (res.status === 404) throw new Error('This backend cannot say who holds the Level 2 lines yet: reload the backend after the update.');
  const body: unknown = await res.json().catch(() => null);
  if (res.status === 401 || res.status === 503) {
    throw new Error('The desk has no API key for this: Nova needs NOVA_API_KEY to change who may take a line.');
  }
  if (!res.ok) {
    const detail = obj(body)?.detail;
    const said = typeof detail === 'string' ? detail : obj(detail)?.error;
    throw new Error(typeof said === 'string' && said ? said : `The desk answered ${res.status}.`);
  }
  const view = normalizeDepthLines(body);
  if (!view) throw new Error('The Level 2 lines answered in a shape this desk does not read.');
  return view;
}

export async function fetchLines(): Promise<DepthLinesView> {
  return read(await novaFetch(`${API_BASE_URL}/api/ibkr/depth/lines`));
}

export async function setLending(on: boolean): Promise<DepthLinesView> {
  if (onSampleDesk()) throw new Error(SAMPLE_WRITE_REFUSAL);
  return read(await novaFetch(`${API_BASE_URL}/api/ibkr/depth/lending`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ on }),
  }));
}
