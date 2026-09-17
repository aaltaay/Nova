/**
 * IBKR CommissionReport display -- never invent from avg_cost - fill.
 */
import { formatMoney } from '../utils/formatMoney';

export function formatCommission(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return `$${n.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  })}`;
}

export function commissionCellTitle(opts: {
  commission?: number | null;
  avgFill?: number | null;
  avgCost?: number | null;
  filledQty?: number | null;
}): string | undefined {
  if (opts.commission == null || !Number.isFinite(opts.commission)) {
    return undefined;
  }
  const parts = [
    `Commission ${formatCommission(opts.commission)} (IBKR CommissionReport)`,
  ];
  if (opts.avgFill != null && Number.isFinite(opts.avgFill)) {
    parts.push(`Avg fill ${formatMoney(opts.avgFill)}`);
  }
  if (
    opts.avgCost != null
    && Number.isFinite(opts.avgCost)
    && opts.avgFill != null
    && Math.abs(opts.avgCost - opts.avgFill) > 1e-6
  ) {
    parts.push(
      `Avg cost ${formatMoney(opts.avgCost)} includes commission -- not a second fill`,
    );
  }
  if ((opts.filledQty ?? 0) <= 0) {
    parts.push('No fill -- commission should stay blank');
  }
  return parts.join(' -- ');
}
