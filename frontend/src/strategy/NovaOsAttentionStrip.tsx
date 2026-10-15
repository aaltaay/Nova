/** Header attention strip for Nova OS events — mute silences sound only. */
import { useEffect, useState } from 'react';
import { DESK_MUTE_REASON, useDeskMuted } from '../sound';
import {
  dismissNovaOsAttention,
  isNovaOsAttentionMuted,
  setNovaOsAttentionMuted,
  subscribeNovaOsAttention,
  type NovaOsAttentionEvent,
} from './novaOsAttention';
import { TickerLink } from '../components/TickerLink';

interface Props {
  /** Mount once near the app root (App.tsx) so a kill switch or expired
   * approval is visible regardless of tab. Suppresses the idle "No alerts"
   * line (every tab would otherwise show it) and floats fixed at the very
   * top of the viewport, above the Dashboard header and the Stock View page
   * alike, since those two trees share no common header component. */
  global?: boolean;
}

export function NovaOsAttentionStrip({ global = false }: Props = {}) {
  const [events, setEvents] = useState<NovaOsAttentionEvent[]>([]);
  const [muted, setMuted] = useState(isNovaOsAttentionMuted);
  const deskMuted = useDeskMuted();
  const soundTitle = deskMuted ? DESK_MUTE_REASON
    : muted ? 'Unmute attention sounds' : 'Mute attention sounds (visuals stay on)';

  useEffect(() => subscribeNovaOsAttention(setEvents), []);

  if (events.length === 0) {
    if (global) return null;
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
          title={soundTitle}
        >
          {muted ? 'Sound off' : 'Sound on'}
        </button>
      </div>
    );
  }

  const top = events[0];
  return (
    <div
      className={`nova-os-attention-strip nova-os-attention-${top.kind}${global ? ' nova-os-attention-strip--global' : ''}`}
      role="status"
    >
      <div className="nova-os-attention-body">
        {top.symbol && <strong><TickerLink symbol={top.symbol} /> </strong>}
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
          title={soundTitle}
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
