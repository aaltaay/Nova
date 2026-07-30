/** News flame cell shared by scanner tables and HOD Momo dock. */
import {
  NEWS_FLAME_HOT_HOURS,
  NEWS_FLAME_WARM_HOURS,
  NEWS_FLAME_MAX_HOURS,
} from '../constants';

export function NewsCell({ newest_headline_at }: { newest_headline_at: string | null }) {
  if (!newest_headline_at) return <span className="na-muted">—</span>;
  const ageHours = (Date.now() - new Date(newest_headline_at).getTime()) / 3_600_000;
  if (ageHours > NEWS_FLAME_MAX_HOURS) return <span className="na-muted">—</span>;
  let colorClass: string;
  if (ageHours <= NEWS_FLAME_HOT_HOURS) colorClass = 'flame-hot';
  else if (ageHours <= NEWS_FLAME_WARM_HOURS) colorClass = 'flame-warm';
  else colorClass = 'flame-cool';
  const label = ageHours < 1 ? `${Math.round(ageHours * 60)}m ago` : `${Math.floor(ageHours)}h ago`;
  return <span className={`news-flame ${colorClass}`} title={label} />;
}
