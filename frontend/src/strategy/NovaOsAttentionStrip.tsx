/** Header attention strip for Nova OS events — mute silences sound only. */
import { useEffect, useState } from 'react';
import {
  dismissNovaOsAttention,
  isNovaOsAttentionMuted,
  setNovaOsAttentionMuted,
  subscribeNovaOsAttention,
  type NovaOsAttentionEvent,
} from './novaOsAttention';

export function NovaOsAttentionStrip() {
  const [events, setEvents] = useState<NovaOsAttentionEvent[]>([]);
  const [muted, setMuted] = useState(isNovaOsAttentionMuted);

  useEffect(() => subscribeNovaOsAttention(setEvents), []);

  if (events.length === 0) {
    return (
      <div className="nova-os-attention-strip nova-os-attention-empty">
        <span className="na-muted">No Nova OS alerts</span>
        <button
          type="button"
          className="nova-os-mute-btn"
          onClick={() => {
            const next = !muted;
            setNovaOsAttentionMuted(next);
            setMuted(next);
          }}
          title={muted ? 'Unmute attention sounds' : 'Mute attention sounds (visuals stay on)'}
        >
          {muted ? 'Sound off' : 'Sound on'}
        </button>
      </div>
    );
  }

  const top = events[0];
  return (
    <div className={`nova-os-attention-strip nova-os-attention-${top.kind}`} role="status">
      <div className="nova-os-attention-body">
        {top.symbol && <strong>{top.symbol} </strong>}
        {top.message}
      </div>
      <div className="nova-os-attention-actions">
        <button
          type="button"
          className="nova-os-mute-btn"
          onClick={() => {
            const next = !muted;
            setNovaOsAttentionMuted(next);
            setMuted(next);
          }}
        >
          {muted ? 'Sound off' : 'Sound on'}
        </button>
        <button type="button" className="nova-os-mute-btn" onClick={() => dismissNovaOsAttention(top.id)}>
          Dismiss
        </button>
      </div>
    </div>
  );
}
