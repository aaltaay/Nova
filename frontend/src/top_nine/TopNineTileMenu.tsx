/** A tile's right-click menu: mute or unmute that stock's sounds for the day. Closes on a pick, Escape,
 * a click elsewhere or the window losing focus. */
import { useEffect, useRef } from 'react';
import { Bell, BellOff } from 'lucide-react';
import {
  TOP_NINE_MUTE_HINT,
  TOP_NINE_MUTE_LABEL,
  TOP_NINE_UNMUTE_HINT,
  TOP_NINE_UNMUTE_LABEL,
} from './topNineConstants';

export interface TopNineMenuAt {
  symbol: string;
  x: number;
  y: number;
}

const MENU_W = 260;
const MENU_H = 64;

export function TopNineTileMenu({ at, muted, onToggle, onClose }: {
  at: TopNineMenuAt;
  muted: boolean;
  onToggle: (symbol: string) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDown = (ev: PointerEvent) => {
      if (!ref.current?.contains(ev.target as Node)) onClose();
    };
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') onClose();
    };
    window.addEventListener('pointerdown', onDown);
    window.addEventListener('keydown', onKey);
    window.addEventListener('blur', onClose);
    return () => {
      window.removeEventListener('pointerdown', onDown);
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('blur', onClose);
    };
  }, [onClose]);

  const left = Math.max(8, Math.min(at.x, window.innerWidth - MENU_W - 8));
  const top = Math.max(8, Math.min(at.y, window.innerHeight - MENU_H - 8));
  return (
    <div ref={ref} className="top-nine-menu" role="menu" style={{ left, top }} data-testid="top-nine-menu">
      <button
        type="button"
        role="menuitem"
        className="top-nine-menu__row"
        data-testid="top-nine-menu-mute"
        autoFocus
        onClick={() => {
          onToggle(at.symbol);
          onClose();
        }}
      >
        <span className={`top-nine-menu__icon${muted ? ' is-on' : ''}`} aria-hidden="true">
          {muted ? <Bell size={15} /> : <BellOff size={15} />}
        </span>
        <span className="top-nine-menu__text">
          <span className="top-nine-menu__label">
            {muted ? TOP_NINE_UNMUTE_LABEL(at.symbol) : TOP_NINE_MUTE_LABEL(at.symbol)}
          </span>
          <span className="top-nine-menu__hint">{muted ? TOP_NINE_UNMUTE_HINT : TOP_NINE_MUTE_HINT}</span>
        </span>
      </button>
    </div>
  );
}
