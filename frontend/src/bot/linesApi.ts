/**
 * IBKR's three Level 2 lines, one per lane (ADR 071), for the Bots page: `GET /api/ibkr/lanes`. The view is read
 * by the one parser the lanes own (`ibkr/lanes`); this page adds its refusals in words -- a backend without the
 * route, a shape it does not read. Read-only: nothing here moves a lane.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL, LANES_PATH } from '../constants';
import { parseLanes, type LanesView } from '../ibkr';

export async function fetchLanes(): Promise<LanesView> {
  const res = await novaFetch(`${API_BASE_URL}${LANES_PATH}`);
  if (res.status === 404) throw new Error('This backend cannot say who holds the Level 2 lines yet: reload the backend after the update.');
  if (!res.ok) throw new Error(`The desk answered ${res.status}.`);
  const view = parseLanes(await res.json().catch(() => null));
  if (!view) throw new Error('The Level 2 lines answered in a shape this desk does not read.');
  return view;
}
