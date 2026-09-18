/**
 * Cursor-anchored T&S min-size filter. Same portal + clamp pattern as the
 * chart context menu; tape-only copy (text box, not chart actions).
 */
import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import {
  TAPE_MIN_SIZE_FILTER_HINT,
  TAPE_MIN_SIZE_FILTER_MENU_HEIGHT_PX,
  TAPE_MIN_SIZE_FILTER_MENU_WIDTH_PX,
  TAPE_MIN_SIZE_FILTER_TITLE,
} from '../constants';
import { tapeFilterMenuPosition } from './tapeMinSizeFilter';

interface Props {
  x: number;
  y: number;
  draft: string;
  onDraftChange: (next: string) => void;
  onClose: () => void;
}

export function TapeMinSizeFilterMenu({
  x,
  y,
  draft,
  onDraftChange,
  onClose,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const pos = tapeFilterMenuPosition({
    x,
    y,
    menuWidth: TAPE_MIN_SIZE_FILTER_MENU_WIDTH_PX,
    menuHeight: TAPE_MIN_SIZE_FILTER_MENU_HEIGHT_PX,
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
  });

  useEffect(() => {
    const input = ref.current?.querySelector('input');
    input?.focus();
    input?.select();
  }, []);

  useEffect(() => {
    const onDown = (event: MouseEvent) => {
      if (ref.current?.contains(event.target as Node)) return;
      onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' || event.key === 'Enter') onClose();
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
      className="ts-filter-menu"
      data-testid="ts-min-size-filter"
      role="dialog"
      aria-label={TAPE_MIN_SIZE_FILTER_TITLE}
      style={{
        top: pos.top,
        left: pos.left,
        minWidth: TAPE_MIN_SIZE_FILTER_MENU_WIDTH_PX,
      }}
      onContextMenu={(event) => event.preventDefault()}
    >
      <label className="ts-filter-menu__label" htmlFor="ts-min-size-input">
        {TAPE_MIN_SIZE_FILTER_TITLE}
      </label>
      <input
        id="ts-min-size-input"
        data-testid="ts-min-size-input"
        className="ts-filter-menu__input"
        type="text"
        inputMode="numeric"
        autoComplete="off"
        value={draft}
        placeholder="0"
        onChange={(event) => onDraftChange(event.target.value)}
      />
      <p className="ts-filter-menu__hint">{TAPE_MIN_SIZE_FILTER_HINT}</p>
    </div>,
    document.body,
  );
}
