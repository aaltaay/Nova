/**
 * HOD Momo / Running Up table columns + header calculation tooltips.
 * Feature-local source of truth (not the shared chart_api barrel).
 */

export const HOD_MOMO_COLUMNS: [string, string][] = [
  ['news', 'News'],
  ['time', 'Time'],
  ['symbol', 'Symbol'],
  ['price', 'Price'],
  ['change_pct', 'Change %'],
  ['rvol', 'RVOL (Daily)'],
  ['rvol_5min', 'RVOL (5m)'],
  ['float', 'Float'],
  ['gap_pct', 'Gap %'],
  ['volume', 'Volume'],
  ['strategy', 'Strategy'],
];

/** One hover bubble per column header explaining the math / row model. */
export const HOD_MOMO_COLUMN_TOOLTIPS: Record<string, string> = {
  news:
    'Newest headline age for this symbol, joined from the scanner news feed. '
    + 'Flame: hot <=2h, warm <=12h, cool <=24h; older or none shows a dash.',
  time:
    'Clock time this symbol FIRST fired a HOD Momo alert today. '
    + 'The row stays pinned to that first catch (position and stamp do not move). '
    + 'Later re-fires do not change Time -- they refresh live metrics '
    + '(price, change %, RVOL, volume, float, gap, strategies).',
  symbol:
    "Ticker. A '(N in Xs)' badge means N alerts of the same strategy fired "
    + 'within X seconds (burst consolidation).',
  price:
    'Last trade price from the newest fire for this symbol (IBKR feed). '
    + 'Updates on later re-fires; Time stays at first catch.',
  change_pct:
    '(price - previous close) / previous close x 100 from the newest fire. '
    + 'Updates on later re-fires.',
  rvol:
    "Daily relative volume from the newest fire: today's volume / average daily volume. "
    + "When the source badge ends in 'pace', it is pace-adjusted: volume / "
    + '(avg volume x elapsed fraction of the 04:00-16:00 ET session). '
    + 'Updates on later re-fires.',
  rvol_5min:
    '5-minute relative volume from the newest fire: volume in the trailing 5 minutes '
    + '/ typical 5-minute volume for this time of day. Updates on later re-fires.',
  float:
    'Shares in the public float (yfinance fundamentals). '
    + 'Refreshed when later fires carry an updated snapshot.',
  gap_pct:
    'Gap vs previous close from the newest enrichment snapshot: '
    + '(price - previous close) / previous close x 100.',
  volume:
    'Total shares traded today from the newest fire. Updates on later re-fires.',
  strategy:
    'Which HOD Momo sub-strategy(ies) fired for this symbol. '
    + 'Stacked pills when several fired (including later re-fires); '
    + 'click the header to filter strategies.',
};
