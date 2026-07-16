/** Pick which scanner feed's last_scan drives the header "updated Xs ago". */

export type ScannerScanAges = {
  gappers: number;
  movers: number;
  afterhours: number;
};

/**
 * Tab-aware freshness. After-hours snapshots freeze after the session ends,
 * so blindly taking the last poll response (afterhours) made Movers look
 * hours stale even while /api/movers was refreshing every few seconds.
 */
export function scanAgeForTab(tab: string, ages: ScannerScanAges): number {
  if (tab === 'gappers') return ages.gappers;
  // Gainers/Losers share the movers feed timestamp (same /api/movers poll).
  if (tab === 'movers' || tab === 'gainers' || tab === 'losers') return ages.movers;
  if (tab === 'afterhours') return ages.afterhours;
  return Math.max(ages.gappers, ages.movers, ages.afterhours);
}
