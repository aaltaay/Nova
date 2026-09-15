import {
  ADVISE_AGENTS_HINT,
  ADVISE_EMPTY_HINT,
  ADVISE_MAX_DEPTH,
  ADVISE_MIN_DEPTH,
  ADVISE_MODEL_LABEL,
} from './constants';
import { useAdvise } from './AdviseContext';

function formatWhen(ts: number | null | undefined): string {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleString();
}

export function AdviseControls() {
  const {
    symbol,
    setSymbol,
    depth,
    setDepth,
    estimate,
    run,
    history,
    busy,
    loadBook,
    loadHistoryRun,
    runDebate,
    cancelDebate,
  } = useAdvise();
  const live = run?.status === 'queued' || run?.status === 'running';

  return (
    <div className="advise-controls">
      <label className="advise-field">
        <span>Symbol</span>
        <input
          data-testid="advise-symbol"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          onBlur={() => void loadBook()}
          placeholder="AAPL"
        />
      </label>
      <label className="advise-field">
        <span>Debate depth</span>
        <input
          data-testid="advise-depth"
          type="number"
          min={ADVISE_MIN_DEPTH}
          max={ADVISE_MAX_DEPTH}
          value={depth}
          onChange={(e) => {
            const next = Number(e.target.value) || ADVISE_MIN_DEPTH;
            setDepth(next);
            void loadBook(symbol, next);
          }}
        />
      </label>
      <label className="advise-field advise-field--grow">
        <span>Past runs</span>
        <select
          data-testid="advise-history"
          value={run?.id ?? ''}
          onChange={(e) => {
            const id = Number(e.target.value);
            if (id) loadHistoryRun(id);
          }}
        >
          <option value="">Select a saved time</option>
          {history.map((row) => (
            <option key={row.id} value={row.id}>
              {formatWhen(row.created_ts)} · {row.status}
            </option>
          ))}
        </select>
      </label>
      <div className="advise-actions">
        <button
          type="button"
          data-testid="advise-run"
          disabled={busy || live || !symbol.trim()}
          onClick={() => void runDebate(false)}
        >
          Run
        </button>
        <button
          type="button"
          data-testid="advise-refresh"
          disabled={busy || live || !symbol.trim()}
          onClick={() => void runDebate(true)}
        >
          Force refresh
        </button>
        <button
          type="button"
          data-testid="advise-cancel"
          disabled={!live}
          onClick={() => void cancelDebate()}
        >
          Cancel
        </button>
      </div>
      <p className="advise-estimate" data-testid="advise-estimate">
        {estimate ? estimate.summary : ADVISE_EMPTY_HINT}
        {' · '}
        {ADVISE_MODEL_LABEL}
      </p>
      <p className="advise-hint">{ADVISE_AGENTS_HINT}</p>
      {run?.created_ts ? (
        <p className="advise-hint">Last run {formatWhen(run.created_ts)}</p>
      ) : null}
    </div>
  );
}
