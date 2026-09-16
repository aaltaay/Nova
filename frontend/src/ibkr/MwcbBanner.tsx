/** Rare desk-wide MWCB Level 1/2/3 banner from Nasdaq Trade Halt RSS. */
import { mwcbBannerLabel, type MwcbDesk } from './mwcbBanner';

interface Props {
  mwcb: MwcbDesk;
}

export function MwcbBanner({ mwcb }: Props) {
  const label = mwcbBannerLabel(mwcb);
  if (!label) return null;
  return (
    <div
      className="mwcb-banner"
      role="status"
      data-testid="mwcb-banner"
      data-level={mwcb?.level}
      data-stale={mwcb?.stale ? '1' : '0'}
    >
      {label}
    </div>
  );
}
