/**
 * Nova OS judgment panel (Stock View dock tab) — ratings + news score.
 * Signal-only; never places orders.
 */
import {
  NOVA_OS_DECISION_LABELS,
  NOVA_OS_TRADER_BRAIN_DISCLOSURE,
  NOVA_OS_TRADER_EXIT_NOTE,
  SETUP_LABELS,
} from '../constants';
import type { IbkrPosition } from '../ibkr/types';
import { decisionClass, NovaOsVerdictDetail } from '../strategy/NovaOsVerdictDetail';
import { useNovaOsDecideSymbol } from '../strategy/useNovaOsDecideSymbol';
import './traderNovaOsBrain.css';

function agoLabel(updatedAt: number | null): string {
  if (updatedAt == null) return '—';
  const sec = Math.max(0, Math.round((Date.now() - updatedAt) / 1000));
  if (sec < 2) return 'just now';
  return `${sec}s ago`;
}

export type TraderNovaOsBrainProps = {
  symbol: string;
  position?: IbkrPosition | null;
};

export function TraderNovaOsBrain({ symbol, position = null }: TraderNovaOsBrainProps) {
  const { decision, loading, error, errorStatus, updatedAt, refresh } =
    useNovaOsDecideSymbol(symbol, true);
  const qty = position != null && Number.isFinite(position.qty) ? position.qty : 0;
  const holding = Math.abs(qty) > 0;
  const verdict = decision?.decision;
  const setupLabel =
    decision?.setup != null
      ? (SETUP_LABELS[decision.setup] ?? decision.setup)
      : null;

  return (
    <section
      className="trader-nova-os-brain"
      data-testid="trader-nova-os-brain"
      aria-label="Nova OS live judgment"
    >
      <div className="trader-nova-os-brain__bar">
        <div className="trader-nova-os-brain__verdict-row">
          {verdict ? (
            <span
              className={`trader-nova-os-brain__chip ${decisionClass(verdict)}`}
              data-testid="trader-nova-os-verdict"
            >
              {NOVA_OS_DECISION_LABELS[verdict] ?? verdict}
            </span>
          ) : (
            <span className="trader-nova-os-brain__chip trader-nova-os-brain__chip--idle">
              {loading ? '…' : '—'}
            </span>
          )}
          {decision && (
            <span className="trader-nova-os-brain__meta" data-testid="trader-nova-os-meta">
              conf {(decision.confidence * 100).toFixed(0)}%
              {setupLabel ? ` · ${setupLabel}` : ''}
              {' · '}
              mode {decision.mode}
              {' · '}
              updated {agoLabel(updatedAt)}
            </span>
          )}
          {!decision && !error && loading && (
            <span className="trader-nova-os-brain__meta">Loading Nova OS…</span>
          )}
          <button
            type="button"
            className="trader-nova-os-brain__refresh linkish"
            onClick={refresh}
          >
            Refresh
          </button>
        </div>
        <p className="trader-nova-os-brain__edu" data-testid="trader-nova-os-edu">
          {NOVA_OS_TRADER_BRAIN_DISCLOSURE}
        </p>
        {holding && (
          <p className="trader-nova-os-brain__exit" data-testid="trader-nova-os-exit-note">
            Holding {qty} — {NOVA_OS_TRADER_EXIT_NOTE}
          </p>
        )}
        {error && (
          <div
            className="trader-nova-os-brain__error"
            role="alert"
            data-testid="trader-nova-os-error"
          >
            {errorStatus === 404
              ? `${symbol.toUpperCase()} not in scanner cache — Nova OS cannot rate this name until it appears in discovery.`
              : error}
          </div>
        )}
      </div>
      {decision && (
        <div className="trader-nova-os-brain__detail">
          <NovaOsVerdictDetail
            decision={decision}
            disclosure={NOVA_OS_TRADER_BRAIN_DISCLOSURE}
            compact
          />
        </div>
      )}
    </section>
  );
}
