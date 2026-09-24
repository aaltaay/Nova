/**
 * The desk diagnostics rows that need a look -- fail, then warn, then unknown
 * -- listed at the very top of the Trading prerequisites panel with their full
 * detail and fix, so the operator sees what is wrong without scrolling or
 * expanding. Each row also stays in its group below; the duplicate is the point.
 */
import {
  DIAG_ATTENTION_STATES,
  DIAG_ATTENTION_TITLE,
  DIAG_FIX_LABEL,
  DIAG_STATE_LABELS,
} from '../constantGroups/diagnostics';
import { DiagRowAction, type DiagActionHandlers } from './DiagnosticsChecklist';
import type { DiagActionKind, DiagRow } from './diagnosticsTypes';
import './diagnosticsChecklist.css';

const RANK: Record<string, number> = Object.fromEntries(DIAG_ATTENTION_STATES.map((s, i) => [s, i]));

/** The rows that need attention, worst state first, API order within a state. */
export function attentionRows(rows: readonly DiagRow[]): DiagRow[] {
  return rows.filter((r) => r.state in RANK).sort((a, b) => RANK[a.state] - RANK[b.state]);
}

interface Props {
  rows: readonly DiagRow[];
  actions: DiagActionHandlers;
  busy?: Partial<Record<DiagActionKind, boolean>>;
}

export function DiagnosticsAttention({ rows, actions, busy }: Props) {
  if (rows.length === 0) return null;
  const worst = rows[0].state;
  return (
    <section
      className={`diag-attn diag-attn--${worst}`}
      data-testid="diag-attention"
      aria-label={DIAG_ATTENTION_TITLE}
    >
      <h3 className="diag-attn__title">
        {DIAG_ATTENTION_TITLE} <span className="diag-attn__count">{rows.length}</span>
      </h3>
      <ul className="diag-attn__list">
        {rows.map((row) => (
          <li key={row.id} className="diag-attn__item" data-testid={`diag-attention-${row.id}`} data-state={row.state}>
            <span className={`diag-dot diag-dot--${row.state}`} aria-hidden />
            <div className="diag-attn__body">
              <div>
                <span className="diag-attn__name">{row.title}</span>
                <span className="diag-attn__state">{DIAG_STATE_LABELS[row.state] ?? row.state}</span>
              </div>
              <div className="diag-attn__detail">{row.detail}</div>
              {row.fix && (
                <div className="diag-attn__fix">
                  {DIAG_FIX_LABEL}: {row.fix}
                </div>
              )}
            </div>
            <DiagRowAction row={row} actions={actions} busy={busy} testId={`diag-attention-action-${row.id}`} />
          </li>
        ))}
      </ul>
    </section>
  );
}
