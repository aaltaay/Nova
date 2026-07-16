/**
 * Sortable panel-order list for Modules menu (Phase 6 dnd-kit).
 * ↑↓ buttons remain for keyboard / a11y fallback.
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
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { getModule } from '../workspace/registry';

interface Props {
  panelOrder: string[];
  onMove: (moduleId: string, direction: 'up' | 'down') => void;
  onReorder: (activeId: string, overId: string) => void;
}

function SortableOrderItem({
  id,
  index,
  total,
  onMove,
}: {
  id: string;
  index: number;
  total: number;
  onMove: (moduleId: string, direction: 'up' | 'down') => void;
}) {
  const title = getModule(id)?.title ?? id;
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.85 : undefined,
  };

  return (
    <li
      ref={setNodeRef}
      style={style}
      className={`modules-menu__order-item${isDragging ? ' modules-menu__order-item--dragging' : ''}`}
      data-layout-order-id={id}
    >
      <button
        type="button"
        className="modules-menu__drag-handle"
        aria-label={`Drag to reorder ${title}`}
        data-layout-drag-handle={id}
        {...attributes}
        {...listeners}
      >
        ⋮⋮
      </button>
      <span className="modules-menu__order-label">{title}</span>
      <span className="modules-menu__order-actions">
        <button
          type="button"
          aria-label={`Move ${title} up`}
          data-layout-move="up"
          data-layout-move-id={id}
          disabled={index === 0}
          onClick={() => onMove(id, 'up')}
        >
          ↑
        </button>
        <button
          type="button"
          aria-label={`Move ${title} down`}
          data-layout-move="down"
          data-layout-move-id={id}
          disabled={index === total - 1}
          onClick={() => onMove(id, 'down')}
        >
          ↓
        </button>
      </span>
    </li>
  );
}

export function LayoutOrderList({ panelOrder, onMove, onReorder }: Props) {
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
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={panelOrder} strategy={verticalListSortingStrategy}>
        <ul className="modules-menu__order-list" data-testid="layout-order-list">
          {panelOrder.map((id, index) => (
            <SortableOrderItem
              key={id}
              id={id}
              index={index}
              total={panelOrder.length}
              onMove={onMove}
            />
          ))}
        </ul>
      </SortableContext>
    </DndContext>
  );
}
