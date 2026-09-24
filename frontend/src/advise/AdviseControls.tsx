import { isAdviseSymbol, normalizeAdviseSymbol } from './adviseSymbol';
import {
  ADVISE_AGENTS_HINT,
  ADVISE_EMPTY_HINT,
  ADVISE_MAX_DEPTH,
  ADVISE_MIN_DEPTH,
  ADVISE_MODEL_LABEL,
  ADVISE_WHY_BUSY,
  ADVISE_WHY_NOTHING_TO_CANCEL,
  ADVISE_WHY_NO_SYMBOL,
  ADVISE_WHY_RUN_LIVE,
  adviseWhyBadSymbol,
  clampAdviseDepth,
} from './constants';
import {
  estimateMatches,
  formatAdviseActualLine,
  formatAdviseCostHeadline,
  formatAdviseHistoryOption,
  formatAdviseTime,
} from './estimateFormat';
import { useAdvise } from './AdviseContext';

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
  const canSpend = isAdviseSymbol(symbol) && !busy && !live;
  const matched = estimateMatches(estimate, symbol, depth);
  const actualLine = formatAdviseActualLine(run?.actual_usd);
  // Why Run / Force refresh is locked (ux/whyTip.ts), in the order the operator can fix it.
  const typed = normalizeAdviseSymbol(symbol);
  const spendWhy = canSpend ? undefined
    : !typed ? ADVISE_WHY_NO_SYMBOL
      : !isAdviseSymbol(typed) ? adviseWhyBadSymbol(typed)
        : busy ? ADVISE_WHY_BUSY : ADVISE_WHY_RUN_LIVE;

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
            setDepth(clampAdviseDepth(Number(e.target.value)));
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
              {formatAdviseHistoryOption(row)}
            </option>
          ))}
        </select>
      </label>
      <div className="advise-cost" data-testid="advise-estimate">
        {matched && estimate ? (
          <>
            <p className="advise-cost__headline" data-testid="advise-estimate-headline">
              {formatAdviseCostHeadline(estimate)}
            </p>
            <p className="advise-cost__summary" data-testid="advise-estimate-summary">
              {estimate.summary}
            </p>
            {actualLine ? (
              <p className="advise-cost__actual">{actualLine}</p>
            ) : null}
          </>
        ) : isAdviseSymbol(symbol) ? (
          <p className="advise-cost__pending" data-testid="advise-estimate-pending">
            Estimating cost...
          </p>
        ) : (
          <p className="advise-hint" data-testid="advise-empty-hint">{ADVISE_EMPTY_HINT}</p>
        )}
        <p className="advise-hint">{ADVISE_MODEL_LABEL}</p>
      </div>
      <div className="advise-actions">
        <button
          type="button"
          data-testid="advise-run"
          disabled={!canSpend}
          data-why={spendWhy}
          onClick={() => void runDebate(false)}
        >
          Run
        </button>
        <button
          type="button"
          data-testid="advise-refresh"
          disabled={!canSpend}
          data-why={spendWhy}
          onClick={() => void runDebate(true)}
        >
          Force refresh
        </button>
        <button
          type="button"
          data-testid="advise-cancel"
          disabled={!live}
          data-why={live ? undefined : ADVISE_WHY_NOTHING_TO_CANCEL}
          onClick={() => void cancelDebate()}
        >
          Cancel
        </button>
      </div>
      <p className="advise-hint">{ADVISE_AGENTS_HINT}</p>
      {run?.created_ts ? (
        <p className="advise-hint">Last run {formatAdviseTime(run.created_ts)}</p>
      ) : null}
    </div>
  );
}
