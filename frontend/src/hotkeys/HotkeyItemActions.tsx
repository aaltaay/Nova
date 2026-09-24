import type { HotkeyRecord } from './types';

/** Why a row action is locked (ux/whyTip.ts). */
const NO_ROW_WHY = 'Select a hotkey row in the table first.';
const MAP_UNAVAILABLE_WHY = 'This view cannot map rows to Nova Actions.';

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
  const rowWhy = selected ? undefined : NO_ROW_WHY;
  const mapWhy = rowWhy ?? (mapDisabledReason || (onMapToNova ? undefined : MAP_UNAVAILABLE_WHY));
  return (
    <div className="hotkey-actions">
      <button type="button" className="btn-secondary" disabled={!selected} data-why={rowWhy} onClick={onEdit}>
        Edit Item
      </button>
      <button type="button" className="btn-secondary" onClick={onAdd}>
        Add New Item
      </button>
      <button
        type="button"
        className="btn-secondary"
        disabled={!selected || !onMapToNova || Boolean(mapDisabledReason)}
        data-why={mapWhy}
        title={mapWhy ? undefined : 'Create a typed Nova Action from this DAS row'}
        onClick={onMapToNova}
      >
        Map to Nova Action
      </button>
      <button
        type="button"
        className="btn-secondary"
        disabled={!selected}
        data-why={rowWhy}
        onClick={onDeleteItem}
      >
        Delete Item
      </button>
      <button
        type="button"
        className="btn-secondary"
        disabled={!selected}
        data-why={rowWhy}
        onClick={onDeleteKey}
      >
        Delete Key
      </button>
    </div>
  );
}
