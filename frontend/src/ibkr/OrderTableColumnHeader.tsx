/**
 * Drag-reorderable table headers (dnd-kit horizontal).
 * Wrap the whole <table> in OrderTableDnd so DndContext is not inside <thead>.
 */
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  horizontalListSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { ReactNode } from 'react';
import { ORDER_TABLE_COLUMN_DRAG_HINT } from '../constants';
import type { ColumnMeta } from './orderTableColumns';

function SortableTh({ meta }: { meta: ColumnMeta }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: meta.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.85 : undefined,
    cursor: 'grab',
  };

  return (
    <th
      ref={setNodeRef}
      style={style}
      className={`${meta.className} ibkr-col--sortable${isDragging ? ' ibkr-col--dragging' : ''}`}
      title={[meta.title, ORDER_TABLE_COLUMN_DRAG_HINT].filter(Boolean).join(' · ')}
      data-column-id={meta.id}
      {...attributes}
      {...listeners}
    >
      {meta.label}
    </th>
  );
}

interface HeaderProps {
  columns: ColumnMeta[];
  onReset?: () => void;
  trailing?: ReactNode;
}

/** Header row only — must sit under OrderTableDnd. */
export function OrderTableColumnHeader({
  columns,
  onReset,
  trailing,
}: HeaderProps) {
  const ids = columns.map((c) => c.id);

  return (
    <tr
      data-testid="order-table-column-header"
      onDoubleClick={(e) => {
        if ((e.target as HTMLElement).closest('[data-column-pinned]')) return;
        onReset?.();
      }}
    >
      <SortableContext items={ids} strategy={horizontalListSortingStrategy}>
        {columns.map((meta) => (
          <SortableTh key={meta.id} meta={meta} />
        ))}
      </SortableContext>
      {trailing}
    </tr>
  );
}

interface DndProps {
  onReorder: (activeId: string, overId: string) => void;
  children: ReactNode;
}

/** Wraps a table so column drag sensors work without invalid thead children. */
export function OrderTableDnd({ onReorder, children }: DndProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    onReorder(String(active.id), String(over.id));
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={handleDragEnd}
    >
      {children}
    </DndContext>
  );
}
