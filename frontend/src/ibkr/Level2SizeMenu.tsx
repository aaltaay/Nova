/**
 * The Level 2 pane's right-click menu: Small / Medium / Large, the current one ticked, and under them the
 * depth chart's switch (ticked while on). Same cursor-anchored portal and clamp as the Time & Sales min-size
 * menu; a pick, a click outside or Escape closes it.
 */
import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Check } from 'lucide-react';
import {
  L2_DEPTH_CHART_MENU_LABEL,
  L2_SIZES,
  L2_SIZE_LABELS,
  L2_SIZE_MENU_HEIGHT_PX,
  L2_SIZE_MENU_TITLE,
  L2_SIZE_MENU_WIDTH_PX,
} from '../constants';
import { tapeFilterMenuPosition } from './tapeMinSizeFilter';
import type { Level2Size } from './level2Size';

interface Props {
  x: number;
  y: number;
  size: Level2Size;
  onPick: (size: Level2Size) => void;
  depthChart: boolean;
  onDepthChart: (on: boolean) => void;
  onClose: () => void;
}

export function Level2SizeMenu({ x, y, size, onPick, depthChart, onDepthChart, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const pos = tapeFilterMenuPosition({
    x,
    y,
    menuWidth: L2_SIZE_MENU_WIDTH_PX,
    menuHeight: L2_SIZE_MENU_HEIGHT_PX,
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
  });

  useEffect(() => {
    ref.current?.querySelector<HTMLButtonElement>('[role="menuitemradio"][aria-checked="true"]')?.focus();
  }, []);

  useEffect(() => {
    const onDown = (event: MouseEvent) => {
      if (ref.current?.contains(event.target as Node)) return;
      onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  return createPortal(
    <div
      ref={ref}
      className="ts-filter-menu l2-size-menu"
      data-testid="l2-size-menu"
      role="menu"
      aria-label={L2_SIZE_MENU_TITLE}
      style={{ top: pos.top, left: pos.left, minWidth: L2_SIZE_MENU_WIDTH_PX }}
      onContextMenu={(event) => event.preventDefault()}
    >
      <div className="ts-filter-menu__label">{L2_SIZE_MENU_TITLE}</div>
      {L2_SIZES.map((option) => {
        const checked = option === size;
        return (
          <button
            key={option}
            type="button"
            role="menuitemradio"
            aria-checked={checked}
            className={`l2-size-menu__item${checked ? ' l2-size-menu__item--on' : ''}`}
            data-testid={`l2-size-${option}`}
            onClick={() => onPick(option)}
          >
            <span>{L2_SIZE_LABELS[option]}</span>
            {checked && <Check size={14} strokeWidth={2.2} aria-hidden="true" />}
          </button>
        );
      })}
      <div className="l2-size-menu__rule" role="separator" />
      <button
        type="button"
        role="menuitemcheckbox"
        aria-checked={depthChart}
        className={`l2-size-menu__item${depthChart ? ' l2-size-menu__item--on' : ''}`}
        data-testid="l2-depth-chart-switch"
        onClick={() => onDepthChart(!depthChart)}
      >
        <span>{L2_DEPTH_CHART_MENU_LABEL}</span>
        {depthChart && <Check size={14} strokeWidth={2.2} aria-hidden="true" />}
      </button>
    </div>,
    document.body,
  );
}
