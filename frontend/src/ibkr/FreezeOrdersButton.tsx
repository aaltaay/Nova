/**
 * Freeze, right of KILL in the header (ADR 072; approved mockup retire-bots v1): the one freeze latch
 * (`/api/kill-switch`, D-037, ADR 042 D) that lived on the Bots page. One click, after the confirm,
 * cancels every working order on Live, Paper and Sim but the stops that protect a position (ADR 048),
 * and refuses every new order, a sell included, until you unfreeze; it sells nothing. Frozen, the same
 * button reads "Frozen · Unfreeze". Its hover says exactly what a click does (operator, 2026-11-13), and
 * after a freeze a card opens under it with what it did on each venue. The sample desk shows it and
 * refuses the write in its own words (killSwitchApi).
 */
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Snowflake, X } from 'lucide-react';
import {
  GLOBAL_BAR_FREEZE_BUSY_WHY,
  GLOBAL_BAR_FREEZE_DID_CLOSE,
  GLOBAL_BAR_FREEZE_DID_FOOT,
  GLOBAL_BAR_FREEZE_DID_HEAD,
  GLOBAL_BAR_FREEZE_DID_NOTHING,
  GLOBAL_BAR_FREEZE_LABEL,
  GLOBAL_BAR_FREEZE_TIP,
  GLOBAL_BAR_FREEZE_TIP_TITLE,
  GLOBAL_BAR_FROZEN_LABEL,
  GLOBAL_BAR_FROZEN_TIP,
  GLOBAL_BAR_FROZEN_TIP_TITLE,
  globalBarFreezeUnreadWhy,
} from '../constantGroups/global_bar';
import { tipProps } from '../ux/hoverTip';
import { sweepWords } from './freezeSweep';
import type { KillSweep } from './killSwitchApi';
import { useKillSwitch } from './useKillSwitch';
import './freezeOrders.css';

type Anchor = { top: number; right: number };

/** What the last freeze did on each venue, under the button until closed or unfrozen. Portaled to <body> at the
 *  button's place, so the header's scroll box never clips it (as KILL's card). */
function FreezeDidCard({ sweep, error, anchor, onClose }: {
  sweep: KillSweep[] | null; error: string | null; anchor: Anchor; onClose: () => void;
}) {
  return createPortal(
    <div className="freeze-orders__did" role="status" data-testid="global-bar-freeze-did"
      style={{ top: anchor.top, right: anchor.right }}>
      <div className="freeze-orders__did-head">
        <b>{GLOBAL_BAR_FREEZE_DID_HEAD}</b>
        <button type="button" className="freeze-orders__did-x" aria-label={GLOBAL_BAR_FREEZE_DID_CLOSE}
          data-testid="global-bar-freeze-did-close" onClick={onClose}>
          <X size={13} aria-hidden />
        </button>
      </div>
      {sweep && sweep.length === 0 ? <span>{GLOBAL_BAR_FREEZE_DID_NOTHING}</span> : null}
      {(sweep ?? []).map(s => (
        <span key={s.venue} className={s.error || s.failed.length ? 'is-bad' : undefined}
          data-testid={`global-bar-freeze-did-${s.venue}`}>
          {sweepWords(s)}
        </span>
      ))}
      {error ? <span className="is-bad" data-testid="global-bar-freeze-error">{error}</span> : null}
      {sweep ? <span className="freeze-orders__did-foot">{GLOBAL_BAR_FREEZE_DID_FOOT}</span> : null}
    </div>,
    document.body,
  );
}

export function FreezeOrdersButton() {
  const freeze = useKillSwitch();
  const frozen = freeze.status?.tripped === true;
  const [showDid, setShowDid] = useState(false);
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const button = useRef<HTMLButtonElement | null>(null);
  // A freeze's answer, or a press that failed, opens the card under the button; unfreezing closes it.
  useEffect(() => {
    if (!freeze.sweep && !freeze.error) return;
    const rect = button.current?.getBoundingClientRect();
    if (rect) setAnchor({ top: rect.bottom + 6, right: Math.max(8, window.innerWidth - rect.right) });
    setShowDid(true);
  }, [freeze.sweep, freeze.error]);
  useEffect(() => {
    if (!frozen && !freeze.error) setShowDid(false);
  }, [frozen, freeze.error]);

  const unread = freeze.status == null;
  const why = freeze.busy ? GLOBAL_BAR_FREEZE_BUSY_WHY : unread ? globalBarFreezeUnreadWhy(freeze.error) : undefined;
  const tip = frozen
    ? tipProps(GLOBAL_BAR_FROZEN_TIP, GLOBAL_BAR_FROZEN_TIP_TITLE)
    : tipProps(GLOBAL_BAR_FREEZE_TIP, GLOBAL_BAR_FREEZE_TIP_TITLE);
  const label = frozen ? GLOBAL_BAR_FROZEN_LABEL : GLOBAL_BAR_FREEZE_LABEL;
  return (
    <span className="freeze-orders">
      <button
        ref={button}
        type="button"
        className={`freeze-orders__btn${frozen ? ' is-frozen' : ''}`}
        data-testid="global-bar-freeze"
        data-frozen={frozen ? 'true' : 'false'}
        aria-pressed={frozen}
        aria-label={frozen ? GLOBAL_BAR_FROZEN_TIP_TITLE : GLOBAL_BAR_FREEZE_TIP_TITLE}
        disabled={freeze.busy || unread}
        data-why={why}
        {...(why ? {} : tip)}
        onClick={() => void freeze.act(!frozen)}
      >
        <Snowflake size={14} aria-hidden />
        <span>{label}</span>
      </button>
      {showDid && anchor && (freeze.sweep || (freeze.error && !unread)) ? (
        <FreezeDidCard sweep={freeze.sweep} error={unread ? null : freeze.error} anchor={anchor}
          onClose={() => setShowDid(false)} />
      ) : null}
    </span>
  );
}
