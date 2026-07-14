/**
 * Thin draggable divider for split layouts. Pair with `useResizableWidth` —
 * this is the one reusable building block for every future "make X
 * adjustable" request (chart/side panel splits, sidebar widths, etc).
 */
interface Props {
  onPointerDown: (e: React.PointerEvent) => void;
  onDoubleClick?: () => void;
  orientation?: 'vertical' | 'horizontal';
  label?: string;
}

export function ResizeHandle({
  onPointerDown,
  onDoubleClick,
  orientation = 'vertical',
  label = 'Resize panel',
}: Props) {
  return (
    <div
      className={`resize-handle resize-handle--${orientation}`}
      onPointerDown={onPointerDown}
      onDoubleClick={onDoubleClick}
      role="separator"
      aria-orientation={orientation}
      aria-label={label}
      title="Drag to resize · double-click to reset"
    />
  );
}
