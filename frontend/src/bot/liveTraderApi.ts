/**
 * The Live Trader bot's routes (ADR 055): its cards, a host's settings, the answer to an ask. Every write goes
 * through the backend's own rules and answers the cards; the sample desk refuses before any request.
 */
import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import { LT_ASKS_PATH, LT_PATH } from '../constantGroups/live_trader';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { messageFromBotApiBody } from './botApiError';
import type { LiveTraderAsksView, LiveTradersView, LtPatch } from './liveTraderTypes';

const URL = `${API_URL}${LT_PATH}`;

async function read<T>(res: Response, what: string): Promise<T> {
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new Error(messageFromBotApiBody(res.status, body ?? {}));
  if (body == null || typeof body !== 'object') throw new Error(`The Live Trader bot's ${what} came back unreadable`);
  return body as T;
}

function refuseOnSampleDesk(): void {
  if (onSampleDesk()) throw new Error(SAMPLE_WRITE_REFUSAL);
}

export async function fetchLiveTraders(): Promise<LiveTradersView> {
  return read<LiveTradersView>(await novaFetch(URL), 'cards');
}

export async function fetchLiveTraderAsks(): Promise<LiveTraderAsksView> {
  return read<LiveTraderAsksView>(await novaFetch(`${API_URL}${LT_ASKS_PATH}`), 'asks');
}

export async function patchLiveTrader(name: string, body: LtPatch): Promise<LiveTradersView> {
  refuseOnSampleDesk();
  const res = await novaFetch(`${URL}/${encodeURIComponent(name)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  return read<LiveTradersView>(res, 'settings');
}

export async function patchLiveTradersAll(body: { sell_all_at: string }): Promise<LiveTradersView> {
  refuseOnSampleDesk();
  const res = await novaFetch(URL, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  return read<LiveTradersView>(res, 'settings');
}

export async function answerLiveTraderAsk(name: string, askId: string, approve: boolean): Promise<LiveTradersView> {
  refuseOnSampleDesk();
  const res = await novaFetch(`${URL}/${encodeURIComponent(name)}/asks/${encodeURIComponent(askId)}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approve }),
  });
  return read<LiveTradersView>(res, 'answer');
}
