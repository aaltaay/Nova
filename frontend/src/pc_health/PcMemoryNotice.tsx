/**
 * The low-memory strip under the header (operator ask, 2026-10-15): while the PC runs short of memory in Nova's
 * trading session, the backend's words -- how much is free, and the process holding the most (name, PID, size,
 * how long it has run). Main window only, beside the update and backend notices. It only warns: no control here
 * acts on a program, and it never takes keyboard focus. Later hides it while the backend's key holds (the same
 * episode and biggest process) and the level gets no worse.
 */
import { useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { PC_MEMORY_LATER_LABEL, PC_MEMORY_POLL_MS } from './pcHealthConstants';
import { hiddenByLater, usePcMemoryNotice, type PcMemoryLater } from './memoryNoticeRead';
import './pcHealth.css';

interface Props {
  pollMs?: number;
  fetchImpl?: typeof fetch;
}

export function PcMemoryNotice({ pollMs = PC_MEMORY_POLL_MS, fetchImpl = novaFetch }: Props = {}) {
  const notice = usePcMemoryNotice(pollMs, fetchImpl);
  const [later, setLater] = useState<PcMemoryLater | null>(null);
  if (!notice || hiddenByLater(notice, later)) return null;
  return (
    <div className="pc-memory-notice" role="status" data-level={notice.level} data-testid="pc-memory-notice">
      <span className="pc-memory-notice__mark" aria-hidden="true">
        !
      </span>
      <span className="pc-memory-notice__text">
        {notice.text}
        <span className="pc-memory-notice__hint"> {notice.hint}</span>
      </span>
      <button
        type="button"
        className="pc-memory-notice__btn"
        onClick={() => setLater({ key: notice.key, level: notice.level })}
      >
        {PC_MEMORY_LATER_LABEL}
      </button>
    </div>
  );
}
