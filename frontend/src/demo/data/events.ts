/**
 * The demo's earnings and split marks for SMPL's daily chart (`GET /api/chart-events/{symbol}`), Nova
 * Marketing Sample Data in the route's own shape: four quarterly reports, one released on an 8-K before its
 * 10-Q, and a 1-for-10 reverse split. Every other symbol has none.
 */
const report = (accession: string, form: string, day: string, label: string, end: string, months: number,
  revenue: number, netIncome: number, eps: number, release: string | null) => ({
  id: `earnings:${accession}`,
  kind: 'earnings',
  day: release ?? day,
  release: release ? { form: '8-K', accession: `${accession}-r`, day: release, filed: release } : null,
  other_releases: [],
  report: { form, accession, day, filed: day },
  report_pending: false,
  said: null,
  fiscal_year: Number(label.slice(0, 4)),
  fiscal_period: label.slice(5),
  period_label: label,
  period_start: null,
  period_end: end,
  period_months: months,
  revenue: { value: revenue, unit: 'USD', form, filed: day },
  net_income: { value: netIncome, unit: 'USD', form, filed: day },
  eps: { value: eps, unit: 'USD/shares', form, filed: day },
  source: 'sec',
});

const SMPL_EARNINGS = [
  report('0000000000-25-000101', '10-Q', '2025-11-13', '2025 Q3', '2025-09-30', 3, 4_120_000, -2_310_000, -0.18, null),
  report('0000000000-26-000102', '10-K', '2026-03-26', '2025 FY', '2025-12-31', 12, 16_480_000, -9_870_000, -0.74, '2026-03-24'),
  report('0000000000-26-000103', '10-Q', '2026-05-14', '2026 Q1', '2026-03-31', 3, 3_950_000, -1_940_000, -1.42, null),
  report('0000000000-26-000104', '10-Q', '2026-08-13', '2026 Q2', '2026-06-30', 3, 4_610_000, -1_120_000, -0.81, null),
];

const SMPL_SPLITS = [{
  id: 'split:2026-04-21', kind: 'split', day: '2026-04-21', ratio: 0.1, new_shares: 1, old_shares: 10, reverse: true,
  sources: ['massive', 'yahoo'], disagreement: null,
}];

export function chartEvents(symbol: string) {
  const smpl = symbol === 'SMPL';
  return {
    symbol, status: 'read', stale: false, error: null, retry_at: null, replay: false, through: null,
    earnings: { status: 'read', source: 'sec', cik: null, name: smpl ? 'Sample Pharma Inc.' : null, error: null,
      releases_known_since: '2016-10-15', foreign_6k: false, scan: null, events: smpl ? SMPL_EARNINGS : [] },
    splits: { status: 'read', error: null, lists: { massive: { status: 'read' }, sec_confirmed: { status: 'read' }, yahoo: { status: 'read' } },
      events: smpl ? SMPL_SPLITS : [] },
  };
}
