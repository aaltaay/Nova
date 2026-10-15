/**
 * The low-memory notice's answer and its read (operator ask, 2026-10-15). The backend decides when there is a
 * notice and writes its words (`GET /api/perf/memory-notice`); the desk draws them. An answer this desk cannot
 * read is no notice -- never a guessed one. Schema: architecture/schema/desk-ops.md ("The low-memory notice").
 */
import { useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { PC_MEMORY_NOTICE_PATH, PC_MEMORY_POLL_MS, PC_MEMORY_READ_TIMEOUT_MS } from './pcHealthConstants';

export type PcMemoryLevel = 'low' | 'nearly_out' | 'easing';

export interface PcMemoryNoticeModel {
  level: PcMemoryLevel;
  /** The episode and its biggest process: Later holds while this does and the level gets no worse. */
  key: string;
  text: string;
  hint: string;
}

/** What Later was pressed on. */
export type PcMemoryLater = { key: string; level: PcMemoryLevel };

const LEVELS: readonly PcMemoryLevel[] = ['low', 'nearly_out', 'easing'];

/** Nearly out is worse than low; easing ranks with low (the same episode, memory back for a minute). */
const RANK: Record<PcMemoryLevel, number> = { easing: 0, low: 0, nearly_out: 1 };

/**
 * Later hides the strip while the key holds and the level is no worse than when it was pressed. On 2026-10-15 the
 * level went from nearly out to low and back four times in one episode: a hide that ended on any change of
 * level would not have held a minute.
 */
export function hiddenByLater(notice: PcMemoryNoticeModel, later: PcMemoryLater | null): boolean {
  return later !== null && later.key === notice.key && RANK[notice.level] <= RANK[later.level];
}

/** The notice in a `schema_version: 1` answer, or null (none now, or an answer this desk cannot read). */
export function parsePcMemoryNotice(body: unknown): PcMemoryNoticeModel | null {
  if (!body || typeof body !== 'object') return null;
  const raw = body as { schema_version?: unknown; notice?: unknown };
  if (raw.schema_version !== 1 || !raw.notice || typeof raw.notice !== 'object') return null;
  const n = raw.notice as Record<string, unknown>;
  if (!LEVELS.includes(n.level as PcMemoryLevel)) return null;
  if (typeof n.key !== 'string' || typeof n.text !== 'string' || !n.text || typeof n.hint !== 'string') return null;
  return { level: n.level as PcMemoryLevel, key: n.key, text: n.text, hint: n.hint };
}

/**
 * Read the notice now and every `pollMs`, one read at a time, each given up after `timeoutMs` so a request a
 * paging PC stalls never stops the next one (Codex review, PR #996). A read given up keeps what the strip shows:
 * a backend too slow to answer is what the strip warns about, and blanking it then would hide the warning when it
 * matters. An answer without a notice, an answer this desk cannot read, or a refused connection (the backend is
 * down: its own banners say so) leaves no notice -- the strip never shows a guessed one.
 */
export function usePcMemoryNotice(
  pollMs: number = PC_MEMORY_POLL_MS,
  fetchImpl: typeof fetch = novaFetch,
  timeoutMs: number = PC_MEMORY_READ_TIMEOUT_MS,
): PcMemoryNoticeModel | null {
  const [notice, setNotice] = useState<PcMemoryNoticeModel | null>(null);
  useEffect(() => {
    let cancelled = false;
    let reading = false;
    const pull = async () => {
      if (reading) return;
      reading = true;
      const gaveUp = new AbortController();
      const timer = window.setTimeout(() => gaveUp.abort(), timeoutMs);
      let next: PcMemoryNoticeModel | null = null;
      try {
        const res = await fetchImpl(`${API_BASE_URL}${PC_MEMORY_NOTICE_PATH}`, { cache: 'no-store', signal: gaveUp.signal });
        if (res.ok) next = parsePcMemoryNotice(await res.json());
      } catch {
        next = null; // refused, or given up (below): never a guessed notice
      } finally {
        window.clearTimeout(timer);
        reading = false;
      }
      if (!cancelled && !gaveUp.signal.aborted) setNotice(next);
    };
    void pull();
    const id = window.setInterval(() => void pull(), pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [fetchImpl, pollMs, timeoutMs]);
  return notice;
}
