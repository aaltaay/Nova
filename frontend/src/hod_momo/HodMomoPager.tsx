import { HOD_MOMO_PAGE_SIZE } from '../constants';

interface Props {
  page: number;
  pageSize?: number;
  total: number;
  onPageChange: (page: number) => void;
}

/** Prev/next pager for the HOD Momo alert list (newest-first pages). */
export function HodMomoPager({
  page,
  pageSize = HOD_MOMO_PAGE_SIZE,
  total,
  onPageChange,
}: Props) {
  if (total <= pageSize) return null;

  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(0, page), pageCount - 1);
  const from = safePage * pageSize + 1;
  const to = Math.min(total, (safePage + 1) * pageSize);

  return (
    <div className="hod-pager" role="navigation" aria-label="HOD alert pages">
      <button
        type="button"
        className="hod-pager-btn"
        disabled={safePage <= 0}
        onClick={() => onPageChange(safePage - 1)}
        aria-label="Previous page"
      >
        ‹ Prev
      </button>
      <span className="hod-pager-label">
        Showing {from}–{to} of {total}
      </span>
      <button
        type="button"
        className="hod-pager-btn"
        disabled={safePage >= pageCount - 1}
        onClick={() => onPageChange(safePage + 1)}
        aria-label="Next page"
      >
        Next ›
      </button>
    </div>
  );
}
