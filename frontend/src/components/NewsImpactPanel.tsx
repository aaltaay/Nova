import type { NewsImpactClass, NewsImpactVerdict } from '../types/newsImpact';
import {
  NEWS_IMPACT_CLASS_LABELS,
  NEWS_IMPACT_CLASS_TOOLTIPS,
  NEWS_IMPACT_FACTOR_TOOLTIPS,
} from '../constants';

interface Props {
  verdict: NewsImpactVerdict | null | undefined;
  loading?: boolean;
}

function classTone(impactClass: NewsImpactClass): string {
  switch (impactClass) {
    case 'moved_price':
      return 'ni-moved';
    case 'attention_only':
      return 'ni-attention';
    case 'no_effect':
      return 'ni-none';
    default:
      return 'ni-unknown';
  }
}

/** Explicit, non-black-box news → ticker / L2 impact panel. */
export function NewsImpactPanel({ verdict, loading }: Props) {
  if (loading && !verdict) {
    return (
      <div className="news-impact-panel ni-loading" title="Loading news impact rules…">
        Evaluating news impact…
      </div>
    );
  }
  if (!verdict) return null;

  const label = NEWS_IMPACT_CLASS_LABELS[verdict.impact_class] ?? verdict.impact_class;
  const tip = NEWS_IMPACT_CLASS_TOOLTIPS[verdict.impact_class] ?? '';

  return (
    <div className={`news-impact-panel ${classTone(verdict.impact_class)}`}>
      <div className="ni-header">
        <span className="ni-badge" title={tip}>
          {label}
        </span>
        <span
          className="ni-confidence"
          title={NEWS_IMPACT_FACTOR_TOOLTIPS.confidence}
        >
          Confidence {(verdict.confidence * 100).toFixed(0)}%
        </span>
        <span className="ni-rule" title={`Rule version ${verdict.rule_version}`}>
          {verdict.rule_version}
        </span>
      </div>
      <p className="ni-summary">{verdict.summary}</p>
      <dl className="ni-factors">
        <div>
          <dt title={NEWS_IMPACT_FACTOR_TOOLTIPS.age}>Age</dt>
          <dd>
            {verdict.age_hours != null ? `${verdict.age_hours.toFixed(2)}h` : '—'} ({verdict.age_bucket})
          </dd>
        </div>
        <div>
          <dt title={NEWS_IMPACT_FACTOR_TOOLTIPS.source}>Source</dt>
          <dd>
            {verdict.source_tier}
            {verdict.confirmed_by_official ? ' · official/major confirmed' : ' · not officially confirmed'}
          </dd>
        </div>
        <div>
          <dt title={NEWS_IMPACT_FACTOR_TOOLTIPS.price}>Price</dt>
          <dd>{verdict.price_reaction}</dd>
        </div>
        <div>
          <dt title={NEWS_IMPACT_FACTOR_TOOLTIPS.attention}>Attention</dt>
          <dd>{verdict.attention}</dd>
        </div>
        <div>
          <dt title={NEWS_IMPACT_FACTOR_TOOLTIPS.l2}>Level 2</dt>
          <dd>{verdict.l2_reaction}</dd>
        </div>
        <div>
          <dt title={NEWS_IMPACT_FACTOR_TOOLTIPS.sentiment}>Sentiment</dt>
          <dd>
            {verdict.sentiment}
            {verdict.sentiment_score != null ? ` (${(verdict.sentiment_score * 100).toFixed(0)}%)` : ''}
          </dd>
        </div>
      </dl>
      <details className="ni-reasons">
        <summary title="Every rule that fired, in order — nothing hidden">Why this verdict</summary>
        <ul>
          {verdict.reasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      </details>
      <div className="ni-ai" title={NEWS_IMPACT_FACTOR_TOOLTIPS.ai}>
        AI reasoning: {verdict.ai_reasoning ?? 'unavailable (Lincoln AI is opt-in — see .env.example)'}
      </div>
    </div>
  );
}
