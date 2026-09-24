/** The alert the setup scanner raises: "XYZ first pullback near 4.52, stop 4.38,
 * tape go". It floats on every tab until the setup triggers, fails or is
 * dismissed. It stages a ticket at most; nothing here places an order. */
import { useState } from 'react';
import { SETUP_KIND_LABELS, SETUPS_STAGE_NO_ENTRY_WHY, TAPE_VERDICT_LABELS, TAPE_VERDICT_TITLES } from '../constants';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { fmtCents, fmtPx } from './setupsFormat';
import { stageSetupTicket } from './stageSetupTicket';
import type { SetupsBoard } from './types';
import './setups.css';

export function SetupsAlertCard({ board }: { board: SetupsBoard | null }) {
  const { openStockView } = useWorkspace();
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(() => new Set());
  const open = (board?.proposals ?? [])
    .filter(p => p.status === 'open' && !dismissed.has(p.id))
    .sort((a, b) => b.created_at - a.created_at);
  const top = open[0];
  if (!top) return null;
  const kind = top.kind ? (SETUP_KIND_LABELS[top.kind] ?? top.kind) : 'Setup';
  const entry = top.entry != null ? top.entry.toFixed(2) : '';
  const dismiss = () => setDismissed(prev => new Set(prev).add(top.id));
  const tapeNow = top.tape_now ?? 'go';
  return (
    <div className="setups-alert" role="status" aria-live="polite">
      <div className="setups-alert-body">
        <strong>{top.symbol}</strong> {kind.toLowerCase()} near the {fmtPx(top.trigger)} trigger.
        {' '}Stop {fmtPx(top.stop)}, risk {fmtCents(top.risk)}, target {fmtPx(top.target1)}.
        {' '}<span className={`setups-tape--${tapeNow}`} title={TAPE_VERDICT_TITLES[tapeNow]}>
          {TAPE_VERDICT_LABELS[tapeNow] ?? tapeNow}
        </span>
        {tapeNow !== 'go' ? <span className="na-muted"> (it said go when this was raised)</span> : null}
        {top.grade ? <span className="na-muted"> · grade {top.grade}</span> : null}
        {open.length > 1 ? <span className="na-muted"> · {open.length - 1} more on the Setups board</span> : null}
        {top.reasons && top.reasons.length > 0 ? (
          <div className="setups-alert-reasons">{top.reasons.join(' · ')}</div>
        ) : null}
      </div>
      <div className="setups-alert-actions">
        <button
          type="button"
          className="setups-stage"
          disabled={!entry}
          data-why={entry ? undefined : SETUPS_STAGE_NO_ENTRY_WHY}
          onClick={() => {
            stageSetupTicket(top.symbol, entry, openStockView);
            dismiss();
          }}
          title={entry ? `Open ${top.symbol} and stage a BUY limit at ${entry}. Nothing is sent until you press Place.` : undefined}
        >
          Stage ticket
        </button>
        <button type="button" className="setups-link" onClick={dismiss}>Dismiss</button>
      </div>
    </div>
  );
}
