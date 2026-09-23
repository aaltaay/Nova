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
}

export function NewsCell({ newest_headline_at, catalyst }: Props) {
  if (catalyst !== undefined) return <VerdictMark catalyst={catalyst} />;
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

function VerdictMark({ catalyst }: { catalyst: CatalystVerdict | null }) {
  const mark = newsMark(catalyst, Date.now());
  switch (mark.kind) {
    case 'flame':
      return <span className={`news-flame ${mark.ageClass}`} title={mark.title} data-news-mark="catalyst" />;
    case 'ring':
      return <span className={`news-flame news-flame--ring ${mark.ageClass}`} title={mark.title} data-news-mark="unplaced" />;
    case 'negative':
      return <span className="news-mark news-mark--negative" title={mark.title} data-news-mark="negative">!</span>;
    case 'pending':
      return <span className="news-mark news-mark--pending" title={mark.title} data-news-mark="pending">H</span>;
    case 'routine':
      return <span className="news-mark news-mark--routine" title={mark.title} data-news-mark="routine" />;
    default:
      return <span className="na-muted" title={mark.title} data-news-mark="none">—</span>;
  }
}
