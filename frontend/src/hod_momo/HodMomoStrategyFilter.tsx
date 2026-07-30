import type { StrategyMeta } from '../constants';

export function StrategyFilterDropdown({
  enabledStrategies,
  counts,
  onToggle,
  onClose,
  configColors,
  filterableStrategies,
}: {
  enabledStrategies: Set<number>;
  counts: Record<number, number>;
  onToggle: (id: number) => void;
  onClose: () => void;
  configColors: Record<number, string>;
  filterableStrategies: StrategyMeta[];
}) {
  return (
    <div className="hod-filter-dropdown">
      <div className="hod-filter-header">
        <span>Filter Strategies</span>
        <button className="hod-filter-close" onClick={onClose}>✕</button>
      </div>
      <label className="hod-filter-row hod-filter-all">
        <input
          type="checkbox"
          checked={
            filterableStrategies.length > 0
            && filterableStrategies.every(s => enabledStrategies.has(s.id))
          }
          onChange={() => {
            const allOn = filterableStrategies.every(s => enabledStrategies.has(s.id));
            filterableStrategies.forEach(s => {
              if (allOn === enabledStrategies.has(s.id)) onToggle(s.id);
            });
          }}
        />
        <span>Select / Unselect All</span>
      </label>
      {filterableStrategies.map(s => {
        const color = configColors[s.id] || s.color;
        return (
          <label key={s.id} className="hod-filter-row">
            <input
              type="checkbox"
              checked={enabledStrategies.has(s.id)}
              onChange={() => onToggle(s.id)}
            />
            <span className="hod-filter-dot" style={{ background: color }} />
            <span className="hod-filter-name">{s.name}</span>
            {(counts[s.id] ?? 0) > 0 && (
              <span className="hod-filter-count">{counts[s.id]}</span>
            )}
          </label>
        );
      })}
    </div>
  );
}
