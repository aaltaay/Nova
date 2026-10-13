/**
 * One followed trader's section: photo and name (read off the stream), on air when the feed's capture lists them
 * now, what they hold and closed that day, and their record over the span picked above the sections.
 */
import {
  FT_CLOSED,
  FT_CLOSED_TODAY,
  FT_HOLDING,
  FT_NAME_FROM_TAG,
  FT_NO_CLOSED,
  FT_NO_CLOSED_TODAY,
  FT_NO_OPEN,
  FT_ON_AIR,
} from './constants';
import { Face, RecordChips } from './parts';
import { ClosedTable, HoldingTable } from './TradeTables';
import type { FollowedRecord, FollowedTrader } from './types';

interface Props {
  trader: FollowedTrader;
  record: FollowedRecord | null;
  onAir: boolean;
  isToday: boolean;
  onProof: (tradeId: string) => void;
}

export function TraderSection({ trader, record, onAir, isToday, onProof }: Props) {
  return (
    <section className="ft-card ft-trader" aria-label={trader.name} data-testid={`ft-trader-${trader.name}`}>
      <div className="ft-trader__head">
        <Face path={trader.face} name={trader.name} size="lg" />
        <div className="ft-trader__who">
          <div className="ft-trader__name-row">
            <span className="ft-trader__name">{trader.name}</span>
            {onAir && <span className="ft-on-air">{FT_ON_AIR}</span>}
          </div>
          <span className="ft-muted ft-small">{FT_NAME_FROM_TAG}</span>
        </div>
        <div className="ft-trader__chips">
          <span className="ft-pill-chip"><b>{trader.open.length}</b> holding</span>
          <span className="ft-pill-chip"><b>{trader.closed.length}</b> {isToday ? 'closed today' : 'closed'}</span>
          <RecordChips record={record} testId={`ft-record-${trader.name}`} />
        </div>
      </div>

      <div className="ft-block">
        <h3 className="ft-block__title">{FT_HOLDING}</h3>
        {trader.open.length === 0
          ? <div className="ft-empty">{FT_NO_OPEN}</div>
          : <HoldingTable trades={trader.open} onProof={onProof} />}
      </div>

      <div className="ft-block">
        <h3 className="ft-block__title">{isToday ? FT_CLOSED_TODAY : FT_CLOSED}</h3>
        {trader.closed.length === 0
          ? <div className="ft-empty">{isToday ? FT_NO_CLOSED_TODAY : FT_NO_CLOSED}</div>
          : <ClosedTable trades={trader.closed} onProof={onProof} />}
      </div>
    </section>
  );
}
