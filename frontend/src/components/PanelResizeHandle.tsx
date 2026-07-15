/**
 * Vertical drag handle between the scanner column and the quote side panel.
 */
interface Props {
  onPointerDown: (e: React.PointerEvent<HTMLElement>) => void;
  dragging?: boolean;
}

export function PanelResizeHandle({ onPointerDown, dragging }: Props) {
  return (
    <div
      className={`panel-resize-handle${dragging ? ' panel-resize-handle--dragging' : ''}`}
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize quote panel"
      title="Drag to resize"
      onPointerDown={onPointerDown}
    />
  );
}
