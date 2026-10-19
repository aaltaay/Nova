/** `/review` query. Desk pane order is 5-minute, 10-second, full day, 1-minute. */

export const REVIEW_TFS = ['1m', '5m', '10s', '1d'] as const;
export type ReviewTf = (typeof REVIEW_TFS)[number];

export const TF_PANE: Record<ReviewTf, { id: string; label: string }> = {
  '5m': { id: '5Min', label: '5-Minute' },
  '10s': { id: '10Sec', label: '10-Second' },
  '1d': { id: '1Day', label: 'Full Day' },
  '1m': { id: '1Min', label: '1-Minute' },
};

const PANE_ORDER: ReviewTf[] = ['5m', '10s', '1d', '1m'];
const ALLOWED = new Set<string>(REVIEW_TFS);

export interface ReviewQuery {
  symbols: string[];
  date: string;
  tfs: ReviewTf[];
  asOf: string;
  fixture: boolean;
  gallery: boolean;
}

export function parseReviewQuery(search: string): ReviewQuery {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  const multi = params.get('symbols');
  const single = params.get('symbol');
  const symbols = (multi ?? single ?? '')
    .split(',')
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
  const asked = params.get('tf');
  const picked = asked
    ? asked.split(',').map((item) => item.trim()).filter((item) => ALLOWED.has(item))
    : [...REVIEW_TFS];
  const tfs = PANE_ORDER.filter((tf) => picked.includes(tf));
  return {
    symbols,
    date: params.get('date') ?? '',
    tfs: tfs.length ? tfs : [...PANE_ORDER],
    asOf: params.get('as_of') ?? '16:00',
    fixture: params.get('fixture') === '1',
    gallery: multi !== null || symbols.length > 1,
  };
}

export function reviewHref(
  symbol: string,
  date: string,
  tfs: readonly string[],
  asOf = '16:00',
  fixture = false,
): string {
  const params = new URLSearchParams();
  params.set('symbol', symbol);
  params.set('date', date);
  params.set('tf', tfs.join(','));
  if (asOf !== '16:00') params.set('as_of', asOf);
  if (fixture) params.set('fixture', '1');
  return `/review?${params.toString()}`;
}
