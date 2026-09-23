/**
 * The strategy cell of a grouped HOD Momo strip row: a count bubble and the
 * strategy chips (S5 S7 S10 ...). Hovering the cell opens a card naming each
 * strategy with what it carried -- momentum over its own window, its burst,
 * and its own raise time when that differs from the row's.
 */
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { hodMomoStripBubbleLabel, hodMomoStripGroupTitle, hodMomoStripStrategyChip } from './hodMomoStripConstants';
import { stripCardPosition, type StripAlertGroup } from './hodMomoStripGroups';
import { alertGateValues, fmtStripClock, stripBurstText } from './hodMomoStripRows';
import type { AlertObject } from './types';

type Props = {
  group: StripAlertGroup;
  strategyColors: Readonly<Record<number, string>>;
};

type Anchor = { left: number; top: number; bottom: number };

export function HodMomoStripStrategies({ group, strategyColors }: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const cardId = useId();
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const { members } = group;
  const names = members.map((m) => m.strategy_name);

  const open = () => {
    const r = ref.current?.getBoundingClientRect();
    if (r) setAnchor({ left: r.left, top: r.top, bottom: r.bottom });
  };
  const close = () => setAnchor(null);

  // The strip scrolls under a still pointer without a mouseleave; the card must not float off its row.
  useEffect(() => {
    if (!anchor) return undefined;
    const onScroll = () => setAnchor(null);
    window.addEventListener('scroll', onScroll, true);
    return () => window.removeEventListener('scroll', onScroll, true);
  }, [anchor]);

  return (
    <span
      ref={ref}
      className="hod-strip__strat hod-strip__strat--group"
      data-testid="hod-momo-strip-group"
      aria-describedby={anchor ? cardId : undefined}
      onMouseEnter={open}
      onMouseLeave={close}
    >
      <span
        className="hod-strip__bubble"
        data-testid="hod-momo-strip-bubble"
        aria-label={hodMomoStripBubbleLabel(members.length, names)}
      >
        {members.length}
      </span>
      {members.map((m) => (
        <span key={m.strategy_id} className="hod-strip__sid">{hodMomoStripStrategyChip(m.strategy_id)}</span>
      ))}
      {anchor ? (
        <StrategyCard id={cardId} anchor={anchor} group={group} strategyColors={strategyColors} />
      ) : null}
    </span>
  );
}

function StrategyCard({
  id,
  anchor,
  group,
  strategyColors,
}: Props & { id: string; anchor: Anchor }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const leadClock = fmtStripClock(group.lead);
  const rows = group.members.length;

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    setPos(stripCardPosition(anchor, { width, height }, { width: window.innerWidth, height: window.innerHeight }));
  }, [anchor, rows]);

  return createPortal(
    <div
      ref={ref}
      id={id}
      role="tooltip"
      className="hod-strip__card"
      data-testid="hod-momo-strip-card"
      style={pos ?? { left: anchor.left, top: anchor.bottom, visibility: 'hidden' }}
    >
      <div className="hod-strip__card-title">
        {hodMomoStripGroupTitle(group.ticker, group.members.length, leadClock)}
      </div>
      {group.members.map((m) => (
        <div key={m.strategy_id} className="hod-strip__card-row" data-testid="hod-momo-strip-card-row">
          <span className="hod-strip__card-dot" style={{ background: strategyColors[m.strategy_id] }} />
          <span className="hod-strip__sid">{hodMomoStripStrategyChip(m.strategy_id)}</span>
          <span className="hod-strip__card-name">{m.strategy_name}</span>
          <span className="hod-strip__card-detail">{memberDetail(m, leadClock)}</span>
        </div>
      ))}
    </div>,
    document.body,
  );
}

/** What this strategy carried that the row's shared values do not say. */
function memberDetail(alert: AlertObject, leadClock: string): string {
  const parts: string[] = [];
  const momo = alertGateValues(alert).find((g) => g.key === 'momentum_pct');
  if (momo && momo.value !== '—') parts.push(`${momo.label} ${momo.value}`);
  const burst = stripBurstText(alert);
  if (burst) parts.push(burst);
  const clock = fmtStripClock(alert);
  if (clock !== leadClock) parts.push(clock);
  return parts.join(' · ');
}
