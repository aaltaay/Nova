/**
 * The Live short proof on the Bot card (ADR 048 step 6, #778 §7): the operator's steps before a short may go to
 * Live, in order, each ticked from what Nova can see -- IBKR's margin account, the $5,000 reset, the five-year
 * tests, three reviewed Paper days with shorts, the four drills with a Paper short open, and the switch the
 * operator sets last. A step only the operator can do says "you"; a step the door enforces says so on hover.
 * Read-only: nothing here completes a step.
 */
import { useEffect, useState } from 'react';
import {
  BOTS_PROOF_COUNT,
  BOTS_PROOF_COUNT_TIP,
  BOTS_PROOF_DONE,
  BOTS_PROOF_ENFORCED_TIP,
  BOTS_PROOF_LEDE,
  BOTS_PROOF_POLL_MS,
  BOTS_PROOF_SEEN_YOU,
  BOTS_PROOF_SEEN_YOU_TIP,
  BOTS_PROOF_SHOWN_TIP,
  BOTS_PROOF_TITLE,
  BOTS_PROOF_UNREAD,
} from '../constantGroups/bots_page';
import { tipProps } from '../ux';
import { prose } from './botsPageFormat';
import { fetchShortProof, type ProofStep, type ShortProofView } from './shortProofApi';
import './botShortProof.css';

export function useShortProof(enabled = true): { view: ShortProofView | null; error: string | null } {
  const [view, setView] = useState<ShortProofView | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled) return undefined;
    let alive = true;
    const read = async () => {
      try {
        const next = await fetchShortProof();
        if (alive) { setView(next); setError(null); }
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : String(err));
      }
    };
    void read();
    const t = setInterval(() => void read(), BOTS_PROOF_POLL_MS);
    return () => { alive = false; clearInterval(t); };
  }, [enabled]);
  return { view, error };
}

const MARK = { done: '✓', todo: '✗', unknown: '?' } as const;

function markOf(step: ProofStep): keyof typeof MARK {
  return step.ok === true ? 'done' : step.ok === false ? 'todo' : 'unknown';
}

function tipOf(step: ProofStep): string {
  const parts = [prose(step.text)];
  if (step.how && step.ok !== true) parts.push(`To do: ${step.how}`);
  parts.push(step.enforced ? BOTS_PROOF_ENFORCED_TIP : BOTS_PROOF_SHOWN_TIP);
  return parts.join('\n\n');
}

function Step({ step }: { step: ProofStep }) {
  const mark = markOf(step);
  return (
    <li className={`bots-proof__step is-${mark}`} data-testid={`bots-proof-step-${step.id}`} data-ok={String(step.ok)}
      {...tipProps(tipOf(step), step.label)}>
      <span className="bots-proof__mark" aria-hidden="true">{MARK[mark]}</span>
      <span className="bots-proof__label">{step.label}</span>
      {step.value ? <span className="bots-proof__value">{step.value}</span> : null}
      {step.seen === 'operator' ? (
        <span className="bots-proof__you" {...tipProps(BOTS_PROOF_SEEN_YOU_TIP)}>{BOTS_PROOF_SEEN_YOU}</span>
      ) : null}
    </li>
  );
}

export function BotShortProof() {
  const { view, error } = useShortProof();
  if (!view) {
    return error ? (
      <section className="bots-proof" data-testid="bots-short-proof">
        <h4 className="bots-proof__title">{BOTS_PROOF_TITLE}</h4>
        <p className="bots-proof__error" role="alert" data-testid="bots-proof-error">{BOTS_PROOF_UNREAD}: {error}</p>
      </section>
    ) : null;
  }
  return (
    <section className="bots-proof" data-testid="bots-short-proof" data-complete={String(view.complete)}>
      <h4 className="bots-proof__title">
        {BOTS_PROOF_TITLE}{' '}
        <span className="bots-proof__count" data-testid="bots-proof-count" {...tipProps(BOTS_PROOF_COUNT_TIP)}>
          {BOTS_PROOF_COUNT(view.done, view.total)}
        </span>
      </h4>
      <p className="bots-proof__lede">{view.complete ? BOTS_PROOF_DONE : BOTS_PROOF_LEDE}</p>
      <ol className="bots-proof__steps">
        {view.steps.map(step => <Step key={step.id} step={step} />)}
      </ol>
      {view.error ? <p className="bots-proof__error" role="alert">{BOTS_PROOF_UNREAD}: {view.error}</p> : null}
      {error ? <p className="bots-proof__error" role="alert">{BOTS_PROOF_UNREAD}: {error}</p> : null}
    </section>
  );
}
