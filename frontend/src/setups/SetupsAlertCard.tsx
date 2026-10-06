/** The alert a setup at Eyes or Strategy raises (ADR 022, ADR 031): "XYZ bull flag near the 4.52 trigger,
 * stop 4.38, tape go". It floats on every tab until the setup triggers, fails or is dismissed (one dismissed
 * list with the Bots inbox). It says when Nova itself takes the proposal or it is not a trade (ADR 042 draft),
 * and then locks Stage with the reason. Stage fills a ticket sized by the venue sleeve's risk per trade --
 * never more: nothing here places an order. */
import { useSyncExternalStore } from 'react';
import {
  SETUP_KIND_LABELS,
  SETUP_TRIGGER_LEVEL_WORDS,
  TAPE_VERDICT_LABELS,
  TAPE_VERDICT_TIPS,
} from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { useConfirmedDeskVenue } from '../ibkr';
import { tipProps } from '../ux/hoverTip';
import { whyProps } from '../ux/whyTip';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { dismiss, dismissedProposals, subscribe } from './proposalDismissals';
import { proposalStageLock, proposalStageSize, proposalVerdictLine, stageLimit } from './proposalVerdict';
import { fmtCents, fmtPx } from './setupsFormat';
import { setupTypeOf } from './setupWords';
import { riskSourceWords, useSleeveRisk } from './sleeveRisk';
import { stageSetupTicket, stageVenueLock } from './stageSetupTicket';
import type { SetupsBoard } from './types';
import './setups.css';

export function SetupsAlertCard({ board }: { board: SetupsBoard | null }) {
  const { openStockView } = useWorkspace();
  const sample = useSampleDataOptional();
  const venue = useConfirmedDeskVenue();
  const dismissed = useSyncExternalStore(subscribe, dismissedProposals, dismissedProposals);
  const open = (board?.proposals ?? [])
    .filter(p => p.status === 'open' && !dismissed.has(p.id))
    .sort((a, b) => b.created_at - a.created_at);
  const top = open[0];
  // The size Stage fills is the sleeve's risk per trade over the risk a share: read it while a card shows.
  const risk = useSleeveRisk(null, Boolean(top) && !sample);
  if (!top) return null;
  const kind = top.kind ? (SETUP_KIND_LABELS[top.kind] ?? top.kind) : 'Setup';
  const limit = stageLimit(top.entry);
  const size = proposalStageSize(top, risk.riskUsd, `${riskSourceWords(risk)} risk per trade`);
  const lock = proposalStageLock(top, size) ?? stageVenueLock(venue, Boolean(sample));
  const verdict = proposalVerdictLine(top);
  const tapeNow = top.tape_now ?? 'go';
  const level = SETUP_TRIGGER_LEVEL_WORDS[setupTypeOf(top)] ?? 'trigger';
  const grade = top.grade ? `${top.grade}${top.pillars ? ` ${top.pillars.passed}/${top.pillars.total}` : ''}` : null;
  const stageTip = `Open ${top.symbol} and stage a BUY limit at ${limit} for ${size.text}. Nothing is sent until you `
    + `press Place.${risk.why ? `\n${risk.why}` : ''}`;
  return (
    <div className={`setups-alert${verdict ? ` setups-alert--${verdict.tone}` : ''}`} role="status" aria-live="polite"
      data-testid="setups-alert">
      <div className="setups-alert-body">
        <strong>{top.symbol}</strong> {kind.toLowerCase()} near the {fmtPx(top.trigger)} {level}.
        {' '}Stop {fmtPx(top.stop)}, risk {fmtCents(top.risk)}, target {fmtPx(top.target1)}.
        {' '}<span className={`setups-tape--${tapeNow}`} {...tipProps(TAPE_VERDICT_TIPS[tapeNow] ?? tapeNow, 'The tape now')}>
          {TAPE_VERDICT_LABELS[tapeNow] ?? tapeNow}
        </span>
        {tapeNow !== 'go' ? <span className="na-muted"> (it said go when this was raised)</span> : null}
        {grade ? <span className="na-muted"> · grade {grade}</span> : null}
        {open.length > 1 ? <span className="na-muted"> · {open.length - 1} more on the Setups board</span> : null}
        {verdict ? (
          <div className={`setups-alert-verdict setups-alert-verdict--${verdict.tone}`} data-testid="setups-alert-verdict">
            {verdict.text}
          </div>
        ) : null}
        {top.reasons && top.reasons.length > 0 ? (
          <div className="setups-alert-reasons">{top.reasons.join(' · ')}</div>
        ) : null}
      </div>
      <div className="setups-alert-actions">
        <button
          type="button"
          className="setups-stage"
          disabled={lock !== null}
          {...whyProps(lock !== null, lock)}
          {...(lock === null ? tipProps(stageTip, 'Stage ticket') : {})}
          onClick={() => {
            if (lock !== null) return;
            if (stageSetupTicket(top.symbol, limit, openStockView, size.qty)) dismiss(top.id);
          }}
          data-testid="setups-alert-stage"
        >
          Stage ticket{lock === null && size.qty !== null ? ` · ${size.qty.toLocaleString('en-US')}` : ''}
        </button>
        <button type="button" className="setups-link" onClick={() => dismiss(top.id)} data-testid="setups-alert-dismiss">
          Dismiss
        </button>
      </div>
    </div>
  );
}
