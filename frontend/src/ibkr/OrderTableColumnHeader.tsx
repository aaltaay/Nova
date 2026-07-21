/**
 * Drag-reorderable + click-to-sort table headers (dnd-kit horizontal).
 * Wrap the whole <table> in OrderTableDnd so DndContext is not inside <thead>.
 * Click = sort · Shift+click = multi-sort · Drag = column reorder · Dbl-click = reset.
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
import {
  ORDER_TABLE_COLUMN_DRAG_HINT,
  ORDER_TABLE_SORT_HINT,
} from '../constants';
import type { ColumnMeta } from './orderTableColumns';
import {
  isOrderSortKey,
  sortLevelFor,
  type OrderSortState,
} from './orderTableSort';

function SortableTh({
  meta,
  sortState,
  onSortColumn,
}: {
  meta: ColumnMeta;
  sortState?: OrderSortState;
  onSortColumn?: (columnId: string, additive: boolean) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: meta.id });
  const canDataSort = Boolean(onSortColumn && isOrderSortKey(meta.id));
  const active = sortState ? sortLevelFor(sortState, meta.id) : null;
  const ariaSort =
    active == null
      ? 'none'
      : active.level.dir === 'asc'
        ? 'ascending'
        : 'descending';

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.85 : undefined,
    cursor: canDataSort ? 'pointer' : 'grab',
  };

  const title = [
    meta.title,
    canDataSort ? ORDER_TABLE_SORT_HINT : ORDER_TABLE_COLUMN_DRAG_HINT,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <th
      ref={setNodeRef}
      style={style}
      className={[
        meta.className,
        'ibkr-col--sortable',
        canDataSort ? 'ibkr-col--data-sort' : '',
        active ? 'ibkr-col--sorted' : '',
        isDragging ? 'ibkr-col--dragging' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      title={title}
      data-column-id={meta.id}
      aria-sort={canDataSort ? ariaSort : undefined}
      onClick={(e) => {
        if (!canDataSort || isDragging) return;
        // Ignore clicks that finish a drag (dnd-kit).
        if (e.defaultPrevented) return;
        onSortColumn?.(meta.id, e.shiftKey);
      }}
      onKeyDown={(e) => {
        if (!canDataSort) return;
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSortColumn?.(meta.id, e.shiftKey);
        }
      }}
      {...attributes}
      {...listeners}
    >
      <span className="ibkr-col-header__label">{meta.label}</span>
      {canDataSort && (
        <span
          className={`ibkr-col-header__sort${active ? ' is-active' : ''}`}
          aria-hidden="true"
        >
          {active
            ? active.level.dir === 'asc'
              ? '↑'
              : '↓'
            : '↕'}
          {active && sortState && sortState.length > 1 ? (
            <sup className="ibkr-col-header__rank">{active.index + 1}</sup>
          ) : null}
        </span>
      )}
    </th>
  );
}

interface HeaderProps {
  columns: ColumnMeta[];
  onReset?: () => void;
  trailing?: ReactNode;
  sortState?: OrderSortState;
  onSortColumn?: (columnId: string, additive: boolean) => void;
  onClearSort?: () => void;
}

/** Header row only — must sit under OrderTableDnd. */
export function OrderTableColumnHeader({
  columns,
  onReset,
  trailing,
  sortState,
  onSortColumn,
  onClearSort,
}: HeaderProps) {
  const ids = columns.map((c) => c.id);
  const hasSort = Boolean(sortState?.length);

  return (
    <tr
      data-testid="order-table-column-header"
      data-sort-active={hasSort ? '1' : undefined}
      onDoubleClick={(e) => {
        if ((e.target as HTMLElement).closest('[data-column-pinned]')) return;
        if (hasSort && onClearSort && (e.altKey || e.metaKey)) {
          onClearSort();
          return;
        }
        onReset?.();
      }}
    >
      <SortableContext items={ids} strategy={horizontalListSortingStrategy}>
        {columns.map((meta) => (
          <SortableTh
            key={meta.id}
            meta={meta}
            sortState={sortState}
            onSortColumn={onSortColumn}
          />
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
