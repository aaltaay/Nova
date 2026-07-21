/**
 * Shared Nova OS decision audit body — gates, news impact, ticket, reasons.
 * Used by Watchlist Decision and Trader always-on brain.
 */
import { NOVA_OS_DECISION_LABELS } from '../constants';
import {
  newsImpactFromDecision,
  type NovaOsNewsImpactEvidence,
} from './novaOsNewsImpact';
import type { NovaOsDecision, NovaOsGateResult } from './types';

function fmtPrice(v: number | null | undefined): string {
  return v == null ? '—' : `$${Number(v).toFixed(2)}`;
}

export function decisionClass(decision: string): string {
  if (decision === 'BUY') return 'nova-os-decision-buy';
  if (decision === 'WAIT') return 'nova-os-decision-wait';
  return 'nova-os-decision-nobuy';
}

export function firstFailedGate(gates: NovaOsGateResult[]): NovaOsGateResult | null {
  return gates.find((g) => !g.passed) ?? null;
}

export function GateRow({
  gate,
  highlight,
}: {
  gate: NovaOsGateResult;
  highlight: boolean;
}) {
  return (
    <li
      className={`nova-os-gate ${gate.passed ? 'nova-os-gate-pass' : 'nova-os-gate-fail'}${highlight ? ' nova-os-gate-first-fail' : ''}`}
      title={gate.reason_codes.join(', ')}
    >
      <span className="nova-os-gate-icon" aria-hidden>
        {gate.passed ? '✓' : '✗'}
      </span>
      <span className="nova-os-gate-name">{gate.name}</span>
      <span className="nova-os-gate-hard">{gate.hard ? 'hard' : 'soft'}</span>
      <span className="nova-os-gate-reasons">
        {gate.reason_codes.join(' · ') || '—'}
      </span>
    </li>
  );
}

function NewsImpactBlock({ news }: { news: NovaOsNewsImpactEvidence }) {
  const confPct = Math.round(news.confidence * 100);
  return (
    <div className="nova-os-news-impact" data-testid="nova-os-news-impact">
      <h4 className="nova-os-section-title">News interpretation</h4>
      <div className="nova-os-news-impact__meta">
        <span className="nova-os-news-impact__class" data-testid="nova-os-news-impact-class">
          {news.impact_class}
        </span>
        <span data-testid="nova-os-news-confidence">conf {confPct}%</span>
        {news.age_bucket && <span>age {news.age_bucket}</span>}
        {news.price_reaction && <span>price {news.price_reaction}</span>}
        {news.attention && <span>attn {news.attention}</span>}
        {news.source_tier && <span>src {news.source_tier}</span>}
      </div>
      {news.headline && (
        <div className="nova-os-news-impact__headline">
          {news.headline_url ? (
            <a href={news.headline_url} target="_blank" rel="noreferrer">
              {news.headline}
            </a>
          ) : (
            news.headline
          )}
        </div>
      )}
      {news.reasons && news.reasons.length > 0 && (
        <ul className="nova-os-news-impact__reasons" data-testid="nova-os-news-reasons">
          {news.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      {news.ai_reasoning && (
        <div className="nova-os-news-impact__ai" data-testid="nova-os-news-ai">
          <span className="na-muted">
            Lincoln narrative (informational — does not authorize size):{' '}
          </span>
          {news.ai_reasoning}
        </div>
      )}
    </div>
  );
}

export type NovaOsVerdictDetailProps = {
  decision: NovaOsDecision;
  /** Extra disclosure under the verdict banner (Trader education copy). */
  disclosure?: string;
  compact?: boolean;
};

export function NovaOsVerdictDetail({
  decision,
  disclosure,
  compact = false,
}: NovaOsVerdictDetailProps) {
  const failed = firstFailedGate(decision.gates);
  const ticket = decision.ticket;
  const news = newsImpactFromDecision(decision);
  const defaultDisclosure = `Signal only. would_execute=${String(decision.would_execute)}; executed=${String(decision.executed)}. Nothing is placed from this panel.`;

  return (
    <div
      className={`nova-os-decision-detail${compact ? ' nova-os-decision-detail--compact' : ''}`}
      data-testid="nova-os-verdict-detail"
    >
      <div className={`nova-os-verdict-banner ${decisionClass(decision.decision)}`}>
        <div>
          <strong>{decision.symbol}</strong>
          {' — '}
          {NOVA_OS_DECISION_LABELS[decision.decision] ?? decision.decision}
          <span className="na-muted">
            {' '}
            · conf {(decision.confidence * 100).toFixed(0)}% · mode {decision.mode} · policy{' '}
            {decision.policy_version}
          </span>
        </div>
        <div className="nova-os-disclosure">{disclosure ?? defaultDisclosure}</div>
      </div>

      {failed && (
        <div className="nova-os-first-fail" role="status">
          First failing gate: <strong>{failed.name}</strong>
          {' — '}
          {failed.reason_codes.join(', ') || 'see evidence'}
        </div>
      )}

      <h4 className="nova-os-section-title">Gates</h4>
      <ul className="nova-os-gate-list">
        {decision.gates.map((g) => (
          <GateRow
            key={g.name}
            gate={g}
            highlight={failed?.name === g.name && !g.passed}
          />
        ))}
      </ul>

      {news && <NewsImpactBlock news={news} />}

      <h4 className="nova-os-section-title">Ticket</h4>
      {ticket ? (
        <div className="nova-os-ticket">
          <span>Entry {fmtPrice(ticket.entry as number | null)}</span>
          <span>Stop {fmtPrice(ticket.stop as number | null)}</span>
          <span>Target {fmtPrice(ticket.target as number | null)}</span>
          <span>Shares {ticket.shares ?? '—'}</span>
          <span>R {ticket.r_multiple ?? '—'}</span>
        </div>
      ) : (
        <div className="na-muted">No ticket — a hard gate failed before sizing.</div>
      )}

      <h4 className="nova-os-section-title">Reason codes</h4>
      <div className="nova-os-reason-row">
        {decision.reason_codes.map((code) => (
          <span key={code} className="pillar-chip">
            {code}
          </span>
        ))}
      </div>

      {!compact && (
        <>
          <h4 className="nova-os-section-title">Citations</h4>
          <ul className="nova-os-citations">
            {decision.citations.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </>
      )}

      {decision.receipt?.id != null && (
        <div className="na-muted nova-os-receipt">
          Receipt #{decision.receipt.id} · action {decision.receipt.action}
        </div>
      )}
    </div>
  );
}
