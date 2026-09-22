/**
 * One HOD Momo strip row -- a single 22 px line, never wrapped:
 * time · ticker · price · NEW · strategy · S<id> · gate values (muted).
 * Row click selects (side panel follows); the ticker opens Trader (ADR 011 §7a).
 */
import { memo } from 'react';
import { TICKER_OPEN_TRADER_TITLE } from '../constants';
import {
  HOD_MOMO_STRIP_NEW_FLAG,
  HOD_MOMO_STRIP_ROW_TITLE,
  hodMomoStripStrategyChip,
} from './hodMomoStripConstants';
import {
  alertGateValues,
  fmtStripClock,
  fmtStripPrice,
  gateValuesAllAbsent,
  HOD_MOMO_STRIP_GATE_ABSENT_TEXT,
  stripPrintNote,
} from './hodMomoStripRows';
import { visibleStrategyTags } from './hodMomoRowLayout';
import type { AlertObject } from './types';

type Props = {
  alert: AlertObject;
  selected: boolean;
  isNew: boolean;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
};

export const HodMomoStripRow = memo(function HodMomoStripRow({
  alert,
  selected,
  isNew,
  onSelect,
  onOpenTrading,
}: Props) {
  const tags = visibleStrategyTags(alert);
  const primary = tags[0] ?? { id: alert.strategy_id, name: alert.strategy_name };
  const extra = tags.length > 1 ? tags.length - 1 : 0;
  const gates = alertGateValues(alert);
  const printNote = stripPrintNote(alert);
  const burst = alert.consolidation_count > 1
    ? `${alert.consolidation_count} in ${Math.max(1, alert.consolidation_span_sec ?? 1)}s`
    : null;

  return (
    <div
      className={`hod-strip__row${selected ? ' is-selected' : ''}${isNew ? ' is-new' : ''}`}
      role="row"
      tabIndex={0}
      aria-selected={selected}
      data-testid="hod-momo-strip-row"
      data-symbol={alert.ticker}
      data-new={isNew ? '1' : undefined}
      title={printNote ? `${HOD_MOMO_STRIP_ROW_TITLE} · ${printNote}` : HOD_MOMO_STRIP_ROW_TITLE}
      onClick={() => onSelect(alert.ticker)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(alert.ticker);
        }
      }}
    >
      <span className="hod-strip__time">{fmtStripClock(alert)}</span>
      <button
        type="button"
        className={`symbol-btn hod-strip__sym${selected ? ' active' : ''}`}
        title={TICKER_OPEN_TRADER_TITLE}
        onClick={(e) => {
          e.stopPropagation();
          onSelect(alert.ticker);
          onOpenTrading(alert.ticker);
        }}
      >
        {alert.ticker}
      </button>
      <span className="hod-strip__price">{fmtStripPrice(alert.price)}</span>
      <span className="hod-strip__new">{isNew ? HOD_MOMO_STRIP_NEW_FLAG : ''}</span>
      <span className="hod-strip__strat" title={tags.map((t) => t.name).join(' · ') || primary.name}>
        {primary.name}
        {extra > 0 ? <span className="hod-strip__strat-more"> +{extra}</span> : null}
      </span>
      <span className="hod-strip__sid" title={primary.name}>
        {hodMomoStripStrategyChip(primary.id)}
      </span>
      {burst ? <span className="hod-strip__burst" title={`${burst} (consolidated)`}>{burst}</span> : null}
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
    </div>
  );
});
