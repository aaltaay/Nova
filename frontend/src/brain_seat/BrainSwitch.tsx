/**
 * The brain's On / Off switch (ADR 072, approved mockup brain-switches v1 sections 1-2): small on the header pill,
 * big in its panel's head -- the twin of Claude's. It flips at once -- Off asks nothing because it sells nothing:
 * the brain's open trade and its stop stay, handed to you -- and the desk sends every press
 * (`PUT /api/traders/brain/switch`), so the backend alone decides: On is refused after the brain's day stop, after
 * its flat-by time or on Live, and that refusal is said in Nova's words where the press was, never swallowed.
 */
import { useCallback, useState } from 'react';
import { setBrainSwitch } from './brainSeatApi';
import { applyBrainSeat } from './brainSeatStore';
import { BRAIN_SWITCH_LABEL, BRAIN_WHY_BUSY, brainSwitchTip } from './brainWords';
import type { BrainSeatStatus } from './types';

export interface BrainSwitchPress {
  busy: boolean;
  /** The last press's refusal in Nova's words; null after a flip that went through. */
  why: string | null;
  flip: (on: boolean) => Promise<void>;
  clearWhy: () => void;
}

export function useBrainSwitch(): BrainSwitchPress {
  const [busy, setBusy] = useState(false);
  const [why, setWhy] = useState<string | null>(null);
  const flip = useCallback(async (on: boolean) => {
    setBusy(true);
    setWhy(null);
    try {
      applyBrainSeat(await setBrainSwitch(on));
    } catch (err) {
      setWhy(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, []);
  const clearWhy = useCallback(() => setWhy(null), []);
  return { busy, why, flip, clearWhy };
}

export function BrainSwitchButton({ status, press, big = false }: {
  status: BrainSeatStatus; press: BrainSwitchPress; big?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={status.on}
      aria-label={BRAIN_SWITCH_LABEL}
      className={`brain-switch${status.on ? ' is-on' : ''}${big ? ' is-big' : ''}`}
      disabled={press.busy}
      data-why={press.busy ? BRAIN_WHY_BUSY : undefined}
      title={brainSwitchTip(status, press.busy)}
      data-testid={big ? 'brain-panel-switch' : 'brain-switch'}
      onClick={(e) => {
        e.stopPropagation();
        void press.flip(!status.on);
      }}
    />
  );
}
