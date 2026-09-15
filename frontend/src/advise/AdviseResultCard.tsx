import { useWorkspace } from '../workspace/WorkspaceContext';
import { ADVISE_DISCLAIMER, ADVISE_STALE_NUDGE } from './constants';
import { useAdvise } from './AdviseContext';
import { stageAdviseTicket } from './ticketFromStance';

export function AdviseResultCard() {
  const { run, retryDebate, busy } = useAdvise();
  const { openStockView } = useWorkspace();
  if (!run) return null;

  const failed = run.status === 'failed' || run.status === 'cancelled';
  const complete = run.status === 'complete';
  const result = run.result;
  const ticket = result?.ticket;

  return (
    <section className="advise-card" data-testid="advise-card">
      <header className="advise-card__head">
        <strong data-testid="advise-stance">{result?.stance || run.status}</strong>
        <span>{run.symbol}</span>
      </header>
      {run.stale ? (
        <p className="advise-stale" data-testid="advise-stale">{ADVISE_STALE_NUDGE}</p>
      ) : null}
      {failed ? (
        <p className="advise-fail" data-testid="advise-fail">
          {run.fail_reason || run.status}
        </p>
      ) : null}
      {complete || result?.reasons?.length ? (
        <>
          <h3>Reasons</h3>
          <ul>{(result?.reasons ?? []).map((item) => <li key={item}>{item}</li>)}</ul>
          <h3>Risks</h3>
          <ul>{(result?.risks ?? []).map((item) => <li key={item}>{item}</li>)}</ul>
        </>
      ) : null}
      <div className="advise-card__actions">
        {ticket ? (
          <button
            type="button"
            data-testid="advise-open-ticket"
            onClick={() => {
              openStockView(run.symbol);
              window.setTimeout(() => {
                stageAdviseTicket(ticket);
              }, 80);
            }}
          >
            Open order ticket
          </button>
        ) : null}
        <button
          type="button"
          data-testid="advise-jump-chart"
          onClick={() => openStockView(run.symbol)}
        >
          Jump to chart
        </button>
        {failed ? (
          <button
            type="button"
            data-testid="advise-retry"
            disabled={busy}
            onClick={() => void retryDebate()}
          >
            Retry
          </button>
        ) : null}
      </div>
      <p className="advise-disclaimer" data-testid="advise-disclaimer">
        {ADVISE_DISCLAIMER}
      </p>
    </section>
  );
}
