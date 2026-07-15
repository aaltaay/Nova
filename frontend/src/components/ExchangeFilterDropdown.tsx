/**
 * Exchange multi-select dropdown reusing the existing HOD Momo filter style.
 * Renders a button that opens a checkbox panel; NASDAQ is on by default.
 */
import { useEffect, useRef } from 'react';
import { SCANNER_EXCHANGE_OPTIONS } from '../constants';
import type { ExchangeFilter } from '../hooks/useExchangeFilter';

interface Props {
  filter: ExchangeFilter;
  onClose: () => void;
}

function ExchangeDropdownPanel({ filter, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, [onClose]);

  const allChecked = filter.selected.length === SCANNER_EXCHANGE_OPTIONS.length;

  return (
    <div className="hod-filter-dropdown exchange-filter-dropdown" ref={ref}>
      <div className="hod-filter-header">
        <span>Filter Exchanges</span>
        <button className="hod-filter-close" onClick={onClose}>✕</button>
      </div>
      <label className="hod-filter-row hod-filter-all">
        <input
          type="checkbox"
          checked={allChecked}
          onChange={() => {
            if (allChecked) {
              // Uncheck all except NASDAQ to avoid empty state
              SCANNER_EXCHANGE_OPTIONS.filter(e => e !== 'NASDAQ').forEach(e =>
                filter.selected.includes(e) && filter.toggle(e),
              );
            } else {
              filter.selectAll();
            }
          }}
        />
        <span>{allChecked ? 'Unselect all' : 'Select all'}</span>
      </label>
      {SCANNER_EXCHANGE_OPTIONS.map(ex => (
        <label key={ex} className="hod-filter-row">
          <input
            type="checkbox"
            checked={filter.selected.includes(ex)}
            onChange={() => filter.toggle(ex)}
          />
          <span className="hod-filter-name">{ex}</span>
        </label>
      ))}
    </div>
  );
}

interface ButtonProps {
  filter: ExchangeFilter;
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
}

export function ExchangeFilterDropdown({ filter, open, onToggle, onClose }: ButtonProps) {
  const summary =
    filter.selected.length === SCANNER_EXCHANGE_OPTIONS.length
      ? 'All exchanges'
      : filter.selected.join(', ') || 'None';

  return (
    <div className="exchange-filter-wrap" style={{ position: 'relative', display: 'inline-block' }}>
      <button
        className="exchange-filter-btn"
        onClick={onToggle}
        title={`Filter by exchange: ${summary}`}
      >
        <span className="exchange-filter-label">Exchanges</span>
        <span className="exchange-filter-summary">{summary}</span>
        <span className="exchange-filter-caret">▾</span>
      </button>
      {open && <ExchangeDropdownPanel filter={filter} onClose={onClose} />}
    </div>
  );
}
