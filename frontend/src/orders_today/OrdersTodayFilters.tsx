/**
 * Webull-style segmented control for Orders (Today).
 */
import { ORDERS_TODAY_FILTERS } from '../constants';
import type { OrdersTodayFilter } from './types';

interface Props {
  value: OrdersTodayFilter;
  onChange: (next: OrdersTodayFilter) => void;
}

export function OrdersTodayFilters({ value, onChange }: Props) {
  return (
    <div
      className="orders-today-filters"
      role="tablist"
      aria-label="Orders today filter"
      data-testid="orders-today-filters"
    >
      {ORDERS_TODAY_FILTERS.map((f) => (
        <button
          key={f.id}
          type="button"
          role="tab"
          aria-selected={value === f.id}
          className={
            value === f.id
              ? 'orders-today-filters__btn is-active'
              : 'orders-today-filters__btn'
          }
          data-filter={f.id}
          data-testid={`orders-today-filter-${f.id}`}
          onClick={() => onChange(f.id)}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}
