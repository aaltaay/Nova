/**
 * Claude's On / Off switch (ADR 072, approved mockup brain-switches v1 sections 1-2): small on the header pill, big
 * in its panel's head. It flips at once -- Off asks nothing because it sells nothing: Claude's open trade and its
 * stop stay, handed to you -- and the desk sends every press (`PUT /api/traders/claude/switch`), so the backend
 * alone decides: On is refused after Claude's day stop, after 15:55 ET or on Live, and that refusal is said in
 * Nova's words where the press was, never swallowed.
 */
import { useCallback, useState } from 'react';
import { setClaudeSwitch } from './claudeSeatApi';
import { applyClaudeSeat } from './claudeSeatStore';
import { CLAUDE_SWITCH_LABEL, CLAUDE_WHY_BUSY, switchTip } from './claudeSeatWords';
import type { ClaudeSwitch } from './types';

export interface ClaudeSwitchPress {
  busy: boolean;
  /** The last press's refusal in Nova's words; null after a flip that went through. */
  why: string | null;
  flip: (sw: ClaudeSwitch) => Promise<void>;
  clearWhy: () => void;
}

export function useClaudeSwitch(): ClaudeSwitchPress {
  const [busy, setBusy] = useState(false);
  const [why, setWhy] = useState<string | null>(null);
  const flip = useCallback(async (sw: ClaudeSwitch) => {
    setBusy(true);
    setWhy(null);
    try {
      applyClaudeSeat(await setClaudeSwitch(!sw.on));
    } catch (err) {
      setWhy(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, []);
  const clearWhy = useCallback(() => setWhy(null), []);
  return { busy, why, flip, clearWhy };
}

export function ClaudeSwitchButton({ sw, press, big = false }: { sw: ClaudeSwitch; press: ClaudeSwitchPress; big?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={sw.on}
      aria-label={CLAUDE_SWITCH_LABEL}
      className={`claude-switch${sw.on ? ' is-on' : ''}${big ? ' is-big' : ''}`}
      disabled={press.busy}
      data-why={press.busy ? CLAUDE_WHY_BUSY : undefined}
      title={switchTip(sw, press.busy)}
      data-testid={big ? 'claude-panel-switch' : 'claude-switch'}
      onClick={(e) => {
        e.stopPropagation();
        void press.flip(sw);
      }}
    />
  );
}
