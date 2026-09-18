/** POST a CSV/JSON trade file to /api/journal/import. Never invents P/L. */
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import type { JournalImportResult } from './types';

const IMPORT_URL = `${API_BASE_URL}/api/journal/import`;

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    const body = detail as JournalImportResult;
    if (body.error) return body.error;
  }
  return 'Import failed';
}

export async function importJournalFile(file: File): Promise<JournalImportResult> {
  const content = await file.text();
  const res = await novaFetch(IMPORT_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: file.name, content }),
  });
  const payload = (await res.json().catch(() => null)) as
    | JournalImportResult
    | { detail?: unknown }
    | null;
  if (!res.ok) {
    const detail =
      payload && typeof payload === 'object' && 'detail' in payload
        ? payload.detail
        : payload;
    const result =
      detail && typeof detail === 'object'
        ? (detail as JournalImportResult)
        : { ok: false, imported: 0, error: detailMessage(detail) };
    throw Object.assign(new Error(result.error || detailMessage(detail)), { result });
  }
  return payload as JournalImportResult;
}
