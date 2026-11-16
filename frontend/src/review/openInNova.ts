/** Ask the review listener to open this symbol in Nova. The API key never leaves the desk. */

export interface OpenInNovaInput {
  symbol: string;
  date: string;
  asOf: string;
}

export interface OpenInNovaResult {
  ok: boolean;
  message: string;
}

function messageFrom(body: unknown): string {
  if (!body || typeof body !== 'object') return '';
  const record = body as Record<string, unknown>;
  if (typeof record.chat_message === 'string' && record.chat_message) return record.chat_message;
  if (typeof record.error === 'string' && record.error) return record.error;
  const detail = record.detail;
  if (detail && typeof detail === 'object') {
    const error = (detail as Record<string, unknown>).error;
    if (typeof error === 'string') return error;
  }
  return '';
}

export async function openInNova(
  input: OpenInNovaInput,
  fetchImpl: typeof fetch = fetch,
): Promise<OpenInNovaResult> {
  const tokenRes = await fetchImpl('/api/review/open-token');
  const tokenBody: unknown = await tokenRes.json().catch(() => null);
  const token = tokenBody && typeof tokenBody === 'object'
    ? (tokenBody as Record<string, unknown>).token
    : null;
  if (!tokenRes.ok || typeof token !== 'string' || !token) {
    return { ok: false, message: messageFrom(tokenBody) || `Could not read the open token (${tokenRes.status})` };
  }
  const res = await fetchImpl('/api/review/open-in-nova', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Nova-Open-Token': token },
    body: JSON.stringify({ symbol: input.symbol, date: input.date, as_of: input.asOf }),
  });
  const body: unknown = await res.json().catch(() => null);
  const message = messageFrom(body) || `Open failed (${res.status})`;
  return { ok: res.ok, message };
}
