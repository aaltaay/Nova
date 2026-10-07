/**
 * SHORT CHECK (ADR 048, #778 step 3): every rule the execution door runs on a short, with its numbers,
 * before the operator presses -- borrow, SSR, the halt, the margin cushion with the liquidation price, the
 * buy stop, the hours, "you hold none long" and equity. The backend's own check answers (`shortCheck`); the
 * box describes, and the door still decides when the short is sent.
 */
import {
  SHORT_CHECK_ALL_PASS,
  SHORT_CHECK_FAILED,
  SHORT_CHECK_LOADING,
  SHORT_CHECK_SUB,
  SHORT_CHECK_TITLE,
  SHORT_CHECK_UNAVAILABLE,
} from '../constantGroups/short_ticket';
import type { ShortCheckRule, ShortCheckState } from './shortCheck';

const MARK: Record<ShortCheckRule['state'], string> = { ok: '✓', bad: '✕', unknown: '?', info: '·' };

function line(rule: ShortCheckRule): string {
  return rule.value ? `${rule.label} · ${rule.value}` : rule.label;
}

export function ShortCheckBox({ state }: { state: ShortCheckState }) {
  const { check, unavailable, error, loading } = state;
  let verdict: string;
  if (unavailable) verdict = '';
  else if (!check) verdict = loading ? SHORT_CHECK_LOADING : '';
  else verdict = check.ok ? SHORT_CHECK_ALL_PASS : check.first?.text ?? '';
  return (
    <section className="short-check" data-testid="short-check" aria-label={SHORT_CHECK_TITLE}>
      <header className="short-check__head">
        <span className="short-check__tag">{SHORT_CHECK_TITLE}</span>
        <span className="short-check__sub">{SHORT_CHECK_SUB}</span>
        {verdict && (
          <span className={`short-check__verdict${check?.ok ? ' is-ok' : ' is-bad'}`} data-testid="short-check-verdict">
            {verdict}
          </span>
        )}
      </header>
      {unavailable && <p className="short-check__note">{SHORT_CHECK_UNAVAILABLE}</p>}
      {!unavailable && error && !check && <p className="short-check__note">{SHORT_CHECK_FAILED(error)}</p>}
      {check && (
        <ul className="short-check__rules">
          {check.rules.map((rule) => (
            <li
              key={`${rule.id}:${rule.label}`}
              className={`short-check__rule is-${rule.state}`}
              data-tip={rule.text || undefined}
              data-tip-title={rule.label}
              data-testid={`short-check-rule-${rule.id}`}
            >
              <span className="short-check__mark" aria-hidden="true">{MARK[rule.state]}</span>
              {line(rule)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
