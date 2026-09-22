/**
 * Webull-style segmented control for Orders (Today). In the Trader drawer it
 * rides on the tab row as status chips, each carrying its count.
 */
import { ORDERS_TODAY_FILTERS } from '../constants';
import { DRAWER_FILTERS_ARIA } from '../constantGroups/trader_chrome';
import type { OrdersTodayFilter } from './types';

interface Props {
  value: OrdersTodayFilter;
  onChange: (next: OrdersTodayFilter) => void;
  /** Rows behind each chip; a missing entry renders no count. */
  counts?: Partial<Record<OrdersTodayFilter, number>>;
}

export function OrdersTodayFilters({ value, onChange, counts }: Props) {
  return (
    <div
      className="orders-today-filters"
      role="tablist"
      aria-label={DRAWER_FILTERS_ARIA}
      data-testid="orders-today-filters"
    >
      {ORDERS_TODAY_FILTERS.map((f) => {
        const count = counts?.[f.id];
        return (
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
            {count != null && (
              <em className="orders-today-filters__count" data-testid={`orders-today-count-${f.id}`}>
                {count}
              </em>
            )}
          </button>
        );
      })}
    </div>
  );
}
