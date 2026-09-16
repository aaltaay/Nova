import { describe, expect, it } from 'vitest';
import { commissionCellTitle, formatCommission } from './orderCommission';

describe('orderCommission', () => {
  it('shows $1.00 for a filled CommissionReport', () => {
    expect(formatCommission(1)).toBe('$1.00');
    expect(formatCommission(1.000003)).toBe('$1.000003');
  });

  it('is blank when no report exists', () => {
    expect(formatCommission(null)).toBe('—');
    expect(formatCommission(undefined)).toBe('—');
    expect(commissionCellTitle({ commission: null, filledQty: 0 })).toBeUndefined();
  });

  it('explains fill vs commission vs avg cost when they differ', () => {
    const title = commissionCellTitle({
      commission: 1,
      avgFill: 150.48,
      avgCost: 151.48,
      filledQty: 1,
    });
    expect(title).toMatch(/Commission \$1\.00/);
    expect(title).toMatch(/Avg fill \$150\.48/);
    expect(title).toMatch(/Avg cost \$151\.48/);
  });
});
