/** Market-wide circuit breaker Level 1/2/3 -- desk banner copy (not LULD tier).
 *
 * Filename is `mwcbDesk` on purpose. `mwcbBanner.ts` next to `MwcbBanner.tsx`
 * collapses on Windows (`tsc` TS1261) and breaks Desktop pack.
 */

export type MwcbDesk = {
  level: number;
  reason_code: string;
  source?: string;
  stale?: boolean;
} | null;

export function mwcbBannerLabel(mwcb: MwcbDesk): string | null {
  if (!mwcb || (mwcb.level !== 1 && mwcb.level !== 2 && mwcb.level !== 3)) {
    return null;
  }
  const stale = mwcb.stale ? ' (RSS stale)' : '';
  return `Market-wide circuit breaker Level ${mwcb.level} (${mwcb.reason_code})${stale}`;
}
