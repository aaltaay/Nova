/**
 * One HOD Momo strip row -- a single 22 px line, never wrapped:
 * time · ticker · price · NEW · strategy · S<id> · gate values (muted).
 * Strategies that fired for the ticker together share the row: a count bubble
 * and their chips, named on hover (HodMomoStripStrategies).
 * Row click selects (side panel follows); the ticker opens Trader (ADR 011 §7a).
 * Right-click opens the symbol menu (watch list, Record, let the bot trade it); a
 * watched ticker's row carries the watch colour on its left edge.
 * `compact` is the same row for a narrow column (the Trader's Focus rail):
 * time · ticker · price · strategy chip(s); the strategy name, burst and gate
 * values move into the row's hover text.
 */
import { memo } from 'react';
import { openBotSymbolMenu } from '../bot';
import { TICKER_OPEN_TRADER_TITLE } from '../constants';
import { useWatchHow, WatchMark, watchMarkTitle } from '../watch_list';
import {
  HOD_MOMO_STRIP_NEW_FLAG,
  HOD_MOMO_STRIP_ROW_TITLE,
  hodMomoStripStrategyChip,
} from './hodMomoStripConstants';
import { sameGroup, type StripAlertGroup } from './hodMomoStripGroups';
import {
  fmtStripClock,
  fmtStripPrice,
  gateValuesAllAbsent,
  gateValuesOf,
  HOD_MOMO_STRIP_GATE_ABSENT_TEXT,
  stripBurstText,
  stripPrintNote,
} from './hodMomoStripRows';
import { HodMomoStripStrategies } from './HodMomoStripStrategies';
import { visibleStrategyTags } from './hodMomoRowLayout';

type Props = {
  group: StripAlertGroup;
  selected: boolean;
  isNew: boolean;
  strategyColors: Readonly<Record<number, string>>;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  /** Draw only time, ticker, price and the strategy chip(s). */
  compact?: boolean;
  /** The keyboard cursor of the list that draws the row. */
  cursor?: boolean;
  testId?: string;
  /** What a click on the row does, for its hover text (the strip: select). */
  rowTitle?: string;
};

function SingleStrategy({ group, compact }: { group: StripAlertGroup; compact: boolean }) {
  const tags = visibleStrategyTags(group.lead);
  const primary = tags[0] ?? { id: group.lead.strategy_id, name: group.lead.strategy_name };
  const extra = tags.length > 1 ? tags.length - 1 : 0;
  if (compact) {
    return (
      <span className="hod-strip__sid" title={tags.map((t) => t.name).join(' · ') || primary.name}>
        {hodMomoStripStrategyChip(primary.id)}{extra > 0 ? ` +${extra}` : ''}
      </span>
    );
  }
  return (
    <>
      <span className="hod-strip__strat" title={tags.map((t) => t.name).join(' · ') || primary.name}>
        {primary.name}
        {extra > 0 ? <span className="hod-strip__strat-more"> +{extra}</span> : null}
      </span>
      <span className="hod-strip__sid" title={primary.name}>
        {hodMomoStripStrategyChip(primary.id)}
      </span>
    </>
  );
}

/** The hidden cells of a compact row, as hover text. */
function compactDetail(group: StripAlertGroup, gates: ReturnType<typeof gateValuesOf>, burst: string | null): string {
  const names = group.members.flatMap((m) => visibleStrategyTags(m).map((t) => t.name));
  const gateText = gateValuesAllAbsent(gates)
    ? HOD_MOMO_STRIP_GATE_ABSENT_TEXT
    : gates.map((g) => `${g.label} ${g.value}`).join(' · ');
  return [[...new Set(names)].join(' · ') || group.lead.strategy_name, burst, gateText].filter(Boolean).join(' · ');
}

/** The biggest burst in the group -- the other members' ride in the hover card. */
function groupBurst(group: StripAlertGroup): string | null {
  let top = group.members[0];
  for (const m of group.members) if (m.consolidation_count > top.consolidation_count) top = m;
  return stripBurstText(top);
}

export const HodMomoStripRow = memo(function HodMomoStripRow({
  group,
  selected,
  isNew,
  strategyColors,
  onSelect,
  onOpenTrading,
  compact = false,
  cursor = false,
  testId = 'hod-momo-strip-row',
  rowTitle = HOD_MOMO_STRIP_ROW_TITLE,
}: Props) {
  const { lead, ticker } = group;
  const how = useWatchHow(ticker);
  const watched = how !== null;
  const grouped = group.members.length > 1;
  const gates = gateValuesOf(group.members);
  const printNote = stripPrintNote(lead);
  const burst = groupBurst(group);

  return (
    <div
      className={`hod-strip__row${compact ? ' hod-strip__row--compact' : ''}${selected ? ' is-selected' : ''}${cursor ? ' is-cursor' : ''}${isNew ? ' is-new' : ''}${watched ? ' is-watched' : ''}`}
      role="row"
      tabIndex={0}
      aria-selected={selected}
      data-testid={testId}
      data-symbol={ticker}
      data-strategies={group.members.length}
      data-new={isNew ? '1' : undefined}
      data-watched={watched ? '1' : undefined}
      title={[
        compact ? compactDetail(group, gates, burst) : null,
        rowTitle,
        printNote,
        how !== null ? watchMarkTitle(ticker, how) : null,
      ].filter(Boolean).join(' · ')}
      onClick={() => onSelect(ticker)}
      onContextMenu={(e) => {
        e.preventDefault();
        openBotSymbolMenu(ticker, e.clientX, e.clientY);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(ticker);
        }
      }}
    >
      <span className="hod-strip__time">{fmtStripClock(lead)}</span>
      <button
        type="button"
        className={`symbol-btn hod-strip__sym${selected ? ' active' : ''}`}
        title={TICKER_OPEN_TRADER_TITLE}
        onClick={(e) => {
          e.stopPropagation();
          onSelect(ticker);
          onOpenTrading(ticker);
        }}
      >
        {ticker}
        {how !== null ? <WatchMark symbol={ticker} className="hod-strip__star" /> : null}
      </button>
      <span className="hod-strip__price">{fmtStripPrice(lead.price)}</span>
      {!compact && <span className="hod-strip__new">{isNew ? HOD_MOMO_STRIP_NEW_FLAG : ''}</span>}
      {grouped
        ? <HodMomoStripStrategies group={group} strategyColors={strategyColors} />
        : <SingleStrategy group={group} compact={compact} />}
      {!compact && burst ? <span className="hod-strip__burst" title={`${burst} (consolidated)`}>{burst}</span> : null}
      {!compact && (
        <span className="hod-strip__gate">
          {gateValuesAllAbsent(gates) ? (
            <span className="hod-strip__gate-absent">{HOD_MOMO_STRIP_GATE_ABSENT_TEXT}</span>
          ) : (
            gates.map((g, i) => (
              <span key={g.key} className="hod-strip__gate-item">
                {i > 0 ? <span className="hod-strip__gate-sep"> · </span> : null}
                <span className="hod-strip__gate-k">{g.label}</span>{' '}
                <b className={g.value === '—' ? 'is-absent' : undefined}>{g.value}</b>
              </span>
            ))
          )}
        </span>
      )}
    </div>
  );
}, (prev, next) => (
  sameGroup(prev.group, next.group)
  && prev.selected === next.selected
  && prev.isNew === next.isNew
  && prev.strategyColors === next.strategyColors
  && prev.onSelect === next.onSelect
  && prev.onOpenTrading === next.onOpenTrading
  && prev.compact === next.compact
  && prev.cursor === next.cursor
  && prev.testId === next.testId
  && prev.rowTitle === next.rowTitle
));
