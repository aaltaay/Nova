import type { HotkeyRecord } from './types';

type Props = {
  selected: HotkeyRecord | null;
  onEdit: () => void;
  onAdd: () => void;
  onDeleteItem: () => void;
  onDeleteKey: () => void;
  onMapToNova?: () => void;
  mapDisabledReason?: string | null;
};

export function HotkeyItemActions({
  selected,
  onEdit,
  onAdd,
  onDeleteItem,
  onDeleteKey,
  onMapToNova,
  mapDisabledReason,
}: Props) {
  return (
    <div className="hotkey-actions">
      <button type="button" disabled={!selected} onClick={onEdit}>
        Edit Item
      </button>
      <button type="button" onClick={onAdd}>
        Add New Item
      </button>
      <button
        type="button"
        className="btn-secondary"
        disabled={!selected || !onMapToNova || Boolean(mapDisabledReason)}
        title={mapDisabledReason ?? 'Create a typed Nova Action from this DAS row'}
        onClick={onMapToNova}
      >
        Map to Nova Action
      </button>
      <button
        type="button"
        className="btn-secondary"
        disabled={!selected}
        onClick={onDeleteItem}
      >
        Delete Item
      </button>
      <button
        type="button"
        className="btn-secondary"
        disabled={!selected}
        onClick={onDeleteKey}
      >
        Delete Key
      </button>
    </div>
  );
}
