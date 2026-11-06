/** The Catalyst cell's mark (`utils/catalystCause.ts`): the News column's marks for news, a dot per cause else. */
import { CATALYST_NONE, CATALYST_READING, CATALYST_SQUEEZE_PIP_TITLE } from '../constants';
import type { CatalystFace } from '../utils/catalystCause';
import './catalystCell.css';
import './catalystNews.css';

export function CatalystMark({ face }: { face: CatalystFace }) {
  const pip = face.squeezePip
    ? <span className="cc-pip" title={CATALYST_SQUEEZE_PIP_TITLE} data-testid="catalyst-squeeze-pip" />
    : null;
  const hollow = face.possible ? ' cc-dot--possible' : '';
  switch (face.mark) {
    case 'flame':
      return <span className={`news-flame ${face.ageClass ?? 'flame-cool'} cc-news`} data-mark="flame">{pip}</span>;
    case 'ring':
      return <span className={`news-flame news-flame--ring ${face.ageClass ?? 'flame-cool'} cc-news`} data-mark="ring">{pip}</span>;
    case 'negative':
      return <span className="news-mark news-mark--negative cc-news" data-mark="negative">!{pip}</span>;
    case 'pending':
      return <span className="news-mark news-mark--pending" data-mark="pending">H</span>;
    case 'routine':
      return <span className="news-mark news-mark--routine" data-mark="routine" />;
    case 'squeeze':
      return <span className={`cc-dot cc-dot--squeeze${hollow}`} data-mark="squeeze" />;
    case 'split':
      return <span className={`cc-dot cc-dot--split${hollow}`} data-mark="split">R</span>;
    case 'lowfloat':
      return <span className={`cc-dot cc-dot--lowfloat${hollow}`} data-mark="lowfloat" />;
    case 'thin':
      return <span className="cc-dot cc-dot--thin" data-mark="thin" />;
    case 'fund':
      return <span className="cc-dot cc-dot--fund" data-mark="fund">F</span>;
    case 'unexplained':
      return <span className="cc-dot cc-dot--unexplained" data-mark="unexplained">?</span>;
    case 'reading':
      return <span className="na-muted cc-none" data-mark="reading">{CATALYST_READING}</span>;
    default:
      return <span className="na-muted cc-none" data-mark="none">{CATALYST_NONE}</span>;
  }
}
