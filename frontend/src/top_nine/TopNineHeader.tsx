/** The pop-up's bar: list tabs with their counts, the legend, where the board comes from, the
 * switch sound and keep-on-top. */
import { etClockSeconds } from './topNineClock';
import {
  TOP_NINE_LEGEND,
  TOP_NINE_LISTS,
  TOP_NINE_ON_TOP_LABEL,
  TOP_NINE_ON_TOP_TITLE,
  TOP_NINE_ON_TOP_WHY,
  TOP_NINE_SOUND_LABEL,
  TOP_NINE_SOUND_TITLE,
  TOP_NINE_TITLE,
  type TopNineList,
} from './topNineConstants';
import type { TopNineSnapshot } from './topNineSnapshot';
import { GridIcon } from './TopNineIcons';

export interface TopNineHeaderProps {
  list: TopNineList;
  onList: (list: TopNineList) => void;
  snapshot: TopNineSnapshot | null;
  now: number;
  sound: boolean;
  onSound: (on: boolean) => void;
  /** null when this window cannot be kept on top (a browser). */
  onTop: boolean | null;
  onOnTop: (on: boolean) => void;
}

function sourceText(snapshot: TopNineSnapshot | null, now: number): { text: string; kind: string } {
  if (!snapshot) return { text: '', kind: 'none' };
  const s = snapshot.source;
  if (s.kind === 'live') return { text: `${etClockSeconds(now)} ET`, kind: 'live' };
  if (s.kind === 'replay') return { text: s.label, kind: 'replay' };
  return { text: s.why, kind: 'unknown' };
}

export function TopNineHeader({ list, onList, snapshot, now, sound, onSound, onTop, onOnTop }: TopNineHeaderProps) {
  const source = sourceText(snapshot, now);
  return (
    <div className="top-nine-bar">
      <div className="top-nine-bar__title">
        <span className="top-nine-bar__mark"><GridIcon size={15} /></span>
        {TOP_NINE_TITLE}
      </div>
      <div className="top-nine-tabs" role="tablist">
        {TOP_NINE_LISTS.map((l) => {
          const total = snapshot?.lists[l.list].total ?? 0;
          return (
            <button
              key={l.list}
              type="button"
              role="tab"
              aria-selected={l.list === list}
              className={`top-nine-tab${l.list === list ? ' is-on' : ''}${total === 0 ? ' is-empty' : ''}`}
              data-testid={`top-nine-tab-${l.list}`}
              onClick={() => onList(l.list)}
            >
              {l.label}
              <small>{total}</small>
            </button>
          );
        })}
      </div>
      <div className="top-nine-legend" aria-hidden="true">
        <span><i className="is-up" />{TOP_NINE_LEGEND.up}</span>
        <span><i className="is-down" />{TOP_NINE_LEGEND.down}</span>
        <span><i className="is-new" />{TOP_NINE_LEGEND.new}</span>
        <span>· {TOP_NINE_LEGEND.hold}</span>
      </div>
      <span className="top-nine-bar__sp" />
      {source.text ? (
        <span className={`top-nine-clock is-${source.kind}`} data-testid="top-nine-source">
          <span className="top-nine-clock__dot" />
          {source.text}
        </span>
      ) : null}
      <button
        type="button"
        className={`top-nine-toggle${sound ? ' is-on' : ''}`}
        aria-pressed={sound}
        title={TOP_NINE_SOUND_TITLE}
        data-testid="top-nine-sound"
        onClick={() => onSound(!sound)}
      >
        {TOP_NINE_SOUND_LABEL}
        <span className="top-nine-toggle__sw" aria-hidden="true" />
      </button>
      <button
        type="button"
        className={`top-nine-toggle${onTop ? ' is-on' : ''}`}
        aria-pressed={onTop === true}
        title={onTop == null ? undefined : TOP_NINE_ON_TOP_TITLE}
        disabled={onTop == null}
        data-why={onTop == null ? TOP_NINE_ON_TOP_WHY : undefined}
        data-testid="top-nine-on-top"
        onClick={() => onOnTop(!onTop)}
      >
        {TOP_NINE_ON_TOP_LABEL}
        <span className="top-nine-toggle__sw" aria-hidden="true" />
      </button>
    </div>
  );
}
