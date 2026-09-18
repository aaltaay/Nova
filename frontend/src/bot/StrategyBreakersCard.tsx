import {
  BOT_BREAKER_HARD_LABEL,
  BOT_BREAKER_HINT,
  BOT_BREAKER_SOFT_LABEL,
  BOT_HARD_BREAKER_USD,
  BOT_SOFT_BREAKER_USD,
} from '../constantGroups/bot';

export function StrategyBreakersCard() {
  return (
    <section className="bot-strategy__card" data-testid="bot-strategy-breakers">
      <h3>Loss breakers</h3>
      <p className="form-hint">{BOT_BREAKER_HINT}</p>
      <div className="bot-strategy__grid">
        <label>
          {BOT_BREAKER_SOFT_LABEL}
          <input
            type="number"
            data-testid="bot-strategy-breaker-soft"
            value={BOT_SOFT_BREAKER_USD}
            disabled
            readOnly
          />
        </label>
        <label>
          {BOT_BREAKER_HARD_LABEL}
          <input
            type="number"
            data-testid="bot-strategy-breaker-hard"
            value={BOT_HARD_BREAKER_USD}
            disabled
            readOnly
          />
        </label>
      </div>
    </section>
  );
}
