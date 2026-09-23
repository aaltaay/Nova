/**
 * The strip header's "⋯" popover: sound toggle, strategy filter, clear,
 * configure, debug. Closes on Escape or a click outside.
 */
import { useEffect, useRef } from 'react';
import { HodMomoSoundToggle } from './HodMomoSoundToggle';
import {
  HOD_MOMO_STRIP_MENU_CLEAR,
  HOD_MOMO_STRIP_MENU_CONFIGURE,
  HOD_MOMO_STRIP_MENU_DEBUG_OFF,
  HOD_MOMO_STRIP_MENU_DEBUG_ON,
  HOD_MOMO_STRIP_MENU_SOUND,
  HOD_MOMO_STRIP_MENU_STRATEGIES,
} from './hodMomoStripConstants';
import { HOD_MOMENTUM_STRATEGY_META } from './scannerPartition';
import { HOD_REPLAY_CLEAR_TITLE } from '../leaderboard/leaderboardConstants';

type Props = {
  showStrategies: boolean;
  visibleStrategies: ReadonlySet<number>;
  strategyCounts: Record<number, number>;
  configColors: Record<number, string>;
  debugOpen: boolean;
  onToggleStrategy: (id: number) => void;
  onClear: () => void;
  /** Sim playback (ADR 022): past alerts are history; there is nothing to clear. */
  clearDisabled?: boolean;
  onConfigure: () => void;
  onToggleDebug: () => void;
  onClose: () => void;
};

export function HodMomoStripMenu({
  showStrategies,
  visibleStrategies,
  strategyCounts,
  configColors,
  debugOpen,
  onToggleStrategy,
  onClear,
  clearDisabled = false,
  onConfigure,
  onToggleDebug,
  onClose,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    const onDown = (e: MouseEvent) => {
      const el = ref.current;
      if (el && !el.contains(e.target as Node)) onClose();
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onDown);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onDown);
    };
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="hod-strip__menu"
      role="menu"
      data-testid="hod-momo-strip-menu"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="hod-strip__menu-row">
        <span>{HOD_MOMO_STRIP_MENU_SOUND}</span>
        <HodMomoSoundToggle className="hod-strip__menu-sound" />
      </div>
      <button type="button" role="menuitem" className="hod-strip__menu-item" onClick={() => { onClear(); onClose(); }} data-testid="hod-momo-dock-clear"
        disabled={clearDisabled} title={clearDisabled ? HOD_REPLAY_CLEAR_TITLE : undefined}>
        {HOD_MOMO_STRIP_MENU_CLEAR}
      </button>
      <button type="button" role="menuitem" className="hod-strip__menu-item" onClick={() => { onConfigure(); onClose(); }} data-testid="hod-momo-dock-configure">
        {HOD_MOMO_STRIP_MENU_CONFIGURE}
      </button>
      <button type="button" role="menuitem" className="hod-strip__menu-item" onClick={() => { onToggleDebug(); onClose(); }} data-testid="hod-momo-strip-debug">
        {debugOpen ? HOD_MOMO_STRIP_MENU_DEBUG_OFF : HOD_MOMO_STRIP_MENU_DEBUG_ON}
      </button>
      {showStrategies ? (
        <div className="hod-strip__menu-strategies" data-testid="hod-momo-strip-strategies">
          <div className="hod-strip__menu-label">{HOD_MOMO_STRIP_MENU_STRATEGIES}</div>
          {HOD_MOMENTUM_STRATEGY_META.map((s) => {
            const color = configColors[s.id] || s.color;
            const count = strategyCounts[s.id] ?? 0;
            return (
              <label key={s.id} className="hod-strip__menu-strategy">
                <input
                  type="checkbox"
                  checked={visibleStrategies.has(s.id)}
                  onChange={() => onToggleStrategy(s.id)}
                />
                <i className="hod-strip__menu-dot" style={{ background: color }} aria-hidden="true" />
                <span className="hod-strip__menu-name">{s.name}</span>
                {count > 0 ? <span className="hod-strip__menu-count">{count}</span> : null}
              </label>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
