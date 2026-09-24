/**
 * The setup templates API (ADR 029): read every setup's parameters and
 * templates; create, edit, delete and put one in play. Writes are refused on
 * the sample desk before any request, like every bot control.
 */
import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { messageFromBotApiBody } from './botApiError';
import { TemplateApiError, type ParamValue, type SetupTemplates, type TemplatesPayload } from './templateTypes';

const TEMPLATES = `${API_URL}/setups/templates`;

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === 'object' && !Array.isArray(v);
}

/** A payload that has the shape the page draws, else null (never a half-read page). */
export function parseTemplatesPayload(raw: unknown): TemplatesPayload | null {
  if (!isRecord(raw) || !Array.isArray(raw.setups)) return null;
  const ok = raw.setups.every(s => isRecord(s) && typeof s.id === 'string' && Array.isArray(s.templates)
    && isRecord(s.catalogue) && Array.isArray((s.catalogue as { groups?: unknown }).groups));
  return ok ? (raw as unknown as TemplatesPayload) : null;
}

async function answer(res: Response): Promise<Record<string, unknown>> {
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = isRecord(body) && isRecord(body.detail) ? body.detail : null;
    throw new TemplateApiError(
      messageFromBotApiBody(res.status, body ?? {}),
      typeof detail?.field === 'string' ? detail.field : null,
      typeof detail?.reason === 'string' ? detail.reason : null,
    );
  }
  if (!isRecord(body)) throw new TemplateApiError(`The templates API answered ${res.status} with no readable body`);
  return body;
}

function refuseOnSampleDesk(): void {
  if (onSampleDesk()) throw new TemplateApiError(SAMPLE_WRITE_REFUSAL);
}

export async function fetchTemplates(): Promise<TemplatesPayload> {
  const parsed = parseTemplatesPayload(await answer(await novaFetch(TEMPLATES)));
  if (!parsed) throw new TemplateApiError('The templates API answered in a shape this page cannot read');
  return parsed;
}

async function write(url: string, method: string, body?: unknown): Promise<SetupTemplates> {
  refuseOnSampleDesk();
  const res = await novaFetch(url, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const out = await answer(res);
  const setup = out.setup;
  if (!isRecord(setup) || !Array.isArray(setup.templates)) {
    throw new TemplateApiError('The templates API answered without the setup it changed');
  }
  return setup as unknown as SetupTemplates;
}

export function createTemplate(setup: string, body: { name: string; from?: string; values?: Record<string, ParamValue> }) {
  return write(`${TEMPLATES}/${encodeURIComponent(setup)}`, 'POST', body);
}

export function updateTemplate(setup: string, id: string,
  body: { name?: string; note?: string; values?: Record<string, ParamValue> }) {
  return write(`${TEMPLATES}/${encodeURIComponent(setup)}/${encodeURIComponent(id)}`, 'PATCH', body);
}

export function deleteTemplate(setup: string, id: string) {
  return write(`${TEMPLATES}/${encodeURIComponent(setup)}/${encodeURIComponent(id)}`, 'DELETE');
}

export function playTemplate(setup: string, id: string) {
  return write(`${TEMPLATES}/${encodeURIComponent(setup)}/${encodeURIComponent(id)}/play`, 'POST');
}
