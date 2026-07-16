import {
  HOTKEY_COMPAT_LABELS,
  type HotkeyCompatStatus,
} from './types';

export type HotkeySortKey = 'name' | 'key' | 'status';

type Props = {
  query: string;
  onQuery: (q: string) => void;
  statusFilter: HotkeyCompatStatus | 'all';
  onStatusFilter: (s: HotkeyCompatStatus | 'all') => void;
  sortKey: HotkeySortKey;
  onSortKey: (k: HotkeySortKey) => void;
};

export function HotkeyFilterToolbar({
  query,
  onQuery,
  statusFilter,
  onStatusFilter,
  sortKey,
  onSortKey,
}: Props) {
  return (
    <div className="hotkey-toolbar">
      <input
        type="search"
        placeholder="Search name, key, command…"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        aria-label="Search hotkeys"
      />
      <select
        value={statusFilter}
        onChange={(e) => onStatusFilter(e.target.value as HotkeyCompatStatus | 'all')}
        aria-label="Filter by compatibility"
      >
        <option value="all">All statuses</option>
        {(Object.keys(HOTKEY_COMPAT_LABELS) as HotkeyCompatStatus[]).map((s) => (
          <option key={s} value={s}>
            {HOTKEY_COMPAT_LABELS[s]}
          </option>
        ))}
      </select>
      <select
        value={sortKey}
        onChange={(e) => onSortKey(e.target.value as HotkeySortKey)}
        aria-label="Sort hotkeys"
      >
        <option value="name">Sort: Name</option>
        <option value="key">Sort: Key</option>
        <option value="status">Sort: Compatibility</option>
      </select>
    </div>
  );
}
