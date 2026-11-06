/**
 * Claude is heard (ADR 068, the approved design's 5): each new event that matters -- a buy set, a fill, a reflex
 * fired, a close, the line taken or given back, a refusal -- pops a toast and the desk's voice says it (the
 * header mute silences it). The first read of the day raises nothing: only what happens while the desk is open.
 */
import { useEffect, useRef, useState } from 'react';
import { speakDesk } from '../sound';
import { useClaudeSeat } from './claudeSeatStore';
import { eventWords, freshToasts } from './claudeSeatWords';
import { ClaudeMark } from './ClaudeMark';
import type { ClaudeEvent } from './types';

export const CLAUDE_TOAST_TTL_MS = 8_000;
const MAX_TOASTS = 4;

function Toast({ event, onDone }: { event: ClaudeEvent; onDone: () => void }) {
  const [held, setHeld] = useState(false);
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    if (held) return undefined;
    const t = window.setTimeout(() => done.current(), CLAUDE_TOAST_TTL_MS);
    return () => window.clearTimeout(t);
  }, [held]);
  return (
    <div className={`claude-toast claude-toast--${event.kind}`} role="status" data-testid="claude-toast"
      onMouseEnter={() => setHeld(true)} onMouseLeave={() => setHeld(false)}>
      <ClaudeMark size={18} />
      <span className="claude-toast__text">{eventWords(event)}</span>
      <button type="button" className="claude-toast__x" aria-label="Dismiss" onClick={onDone}>×</button>
    </div>
  );
}

export function ClaudeSeatToasts() {
  const { status } = useClaudeSeat();
  const since = useRef<number | null>(null);
  const [toasts, setToasts] = useState<ClaudeEvent[]>([]);

  useEffect(() => {
    if (!status) return;
    const newest = status.events[0]?.at ?? 0;
    if (since.current === null) { // the first read: what happened before the desk looked is not news
      since.current = newest;
      return;
    }
    const fresh = freshToasts(status.events, since.current);
    since.current = Math.max(since.current, newest);
    if (!fresh.length) return;
    for (const e of fresh) speakDesk(eventWords(e));
    setToasts(list => [...list, ...fresh].slice(-MAX_TOASTS));
  }, [status]);

  if (!toasts.length) return null;
  return (
    <div className="claude-toasts" role="region" aria-label="Claude's moves" data-testid="claude-toasts">
      {toasts.map(e => (
        <Toast key={`${e.at}-${e.kind}`} event={e}
          onDone={() => setToasts(list => list.filter(t => t !== e))} />
      ))}
    </div>
  );
}
