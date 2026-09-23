/** News flame cell shared by scanner tables and HOD Momo dock. */
import {
  NEWS_FLAME_HOT_HOURS,
  NEWS_FLAME_WARM_HOURS,
  NEWS_FLAME_MAX_HOURS,
} from '../constants';
import type { CatalystVerdict } from '../types/catalystVerdict';
import { newsMark } from '../utils/catalystVerdict';
import './catalystNews.css';

interface Props {
  newest_headline_at: string | null;
  /**
   * The catalyst verdict (ADR 024) when the row carries one: the cell then says what the news is --
   * a flame only for a real catalyst -- instead of lighting up for any article (a movers list, a
   * market wrap). `null` is a verdict not read yet; `undefined` (a row without the field: the
   * Catalysts list, a played-back board) keeps the headline-age flame.
   */
  catalyst?: CatalystVerdict | null;
  /** Drop the native `title` tooltip: the caller shows its own hover card (the Focus rail). */
  plain?: boolean;
}

export function NewsCell({ newest_headline_at, catalyst, plain = false }: Props) {
  if (catalyst !== undefined) return <VerdictMark catalyst={catalyst} plain={plain} />;
  if (!newest_headline_at) return <span className="na-muted">—</span>;
  const ageHours = (Date.now() - new Date(newest_headline_at).getTime()) / 3_600_000;
  if (ageHours > NEWS_FLAME_MAX_HOURS) return <span className="na-muted">—</span>;
  let colorClass: string;
  if (ageHours <= NEWS_FLAME_HOT_HOURS) colorClass = 'flame-hot';
  else if (ageHours <= NEWS_FLAME_WARM_HOURS) colorClass = 'flame-warm';
  else colorClass = 'flame-cool';
  const label = ageHours < 1 ? `${Math.round(ageHours * 60)}m ago` : `${Math.floor(ageHours)}h ago`;
  return <span className={`news-flame ${colorClass}`} title={plain ? undefined : label} />;
}

function VerdictMark({ catalyst, plain }: { catalyst: CatalystVerdict | null; plain: boolean }) {
  const mark = newsMark(catalyst, Date.now());
  const title = plain ? undefined : mark.title;
  switch (mark.kind) {
    case 'flame':
      return <span className={`news-flame ${mark.ageClass}`} title={title} data-news-mark="catalyst" />;
    case 'ring':
      return <span className={`news-flame news-flame--ring ${mark.ageClass}`} title={title} data-news-mark="unplaced" />;
    case 'negative':
      return <span className="news-mark news-mark--negative" title={title} data-news-mark="negative">!</span>;
    case 'pending':
      return <span className="news-mark news-mark--pending" title={title} data-news-mark="pending">H</span>;
    case 'routine':
      return <span className="news-mark news-mark--routine" title={title} data-news-mark="routine" />;
    default:
      return <span className="na-muted" title={title} data-news-mark="none">—</span>;
  }
}
