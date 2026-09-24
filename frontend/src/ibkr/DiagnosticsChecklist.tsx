/**
 * Desk diagnostics checklist (ADR 021): every fact the API process sees,
 * grouped, each row with a state dot, a one-line detail and -- expanded -- its
 * cause, fix and raw evidence. Row actions render only when the desk has a
 * real handler for them; a Copy button puts the plain-text bundle on the
 * clipboard for an issue or a chat.
 */
import { useMemo, useState } from 'react';
import {
  DIAG_CAUSE_LABEL,
  DIAG_COPIED_LABEL,
  DIAG_COPY_FAILED,
  DIAG_COPY_LABEL,
  DIAG_COUNTS_ORDER,
  DIAG_EVIDENCE_LABEL,
  DIAG_FIX_LABEL,
  DIAG_LEAD,
  DIAG_REFRESH_LABEL,
  DIAG_SINCE_LABEL,
  DIAG_STATE_LABELS,
  DIAG_TITLE,
} from '../constantGroups/diagnostics';
import type { DiagActionKind, DiagnosticsPayload, DiagRow } from './diagnosticsTypes';
import './diagnosticsChecklist.css';

export type DiagActionHandlers = Partial<Record<DiagActionKind, () => void>>;

interface Props {
  data: DiagnosticsPayload;
  actions: DiagActionHandlers;
  busy?: Partial<Record<DiagActionKind, boolean>>;
  onRefresh: () => void;
  copyBundle: () => Promise<string>;
}

function sinceLabel(since: number | null): string | null {
  if (since == null || !Number.isFinite(since)) return null;
  const d = new Date(since * 1000);
  return Number.isNaN(d.getTime()) ? null : d.toLocaleTimeString();
}

/** A row's action button, only when the desk has a real handler for its kind. */
export function DiagRowAction({ row, actions, busy, testId }: {
  row: DiagRow;
  actions: DiagActionHandlers;
  busy: Props['busy'];
  testId: string;
}) {
  const kind = row.action?.kind as DiagActionKind | undefined;
  const handler = kind ? actions[kind] : undefined;
  if (!handler || !row.action) return null;
  return (
    <button
      type="button"
      className="diag-row__action"
      onClick={handler}
      disabled={Boolean(kind && busy?.[kind])}
      data-testid={testId}
    >
      {row.action.label}
    </button>
  );
}

function Row({ row, actions, busy }: { row: DiagRow; actions: DiagActionHandlers; busy: Props['busy'] }) {
  const [open, setOpen] = useState(false);
  const since = sinceLabel(row.since);
  return (
    <li className={`diag-row diag-row--${row.state}`} data-testid={`diag-row-${row.id}`} data-state={row.state}>
      <button
        type="button"
        className="diag-row__head"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        data-testid={`diag-row-toggle-${row.id}`}
      >
        <span className={`diag-dot diag-dot--${row.state}`} aria-hidden />
        <span className="diag-row__title">{row.title}</span>
        <span className="diag-row__state">{DIAG_STATE_LABELS[row.state] ?? row.state}</span>
        <span className="diag-row__detail">{row.detail}</span>
      </button>
      <DiagRowAction row={row} actions={actions} busy={busy} testId={`diag-row-action-${row.id}`} />
      {open && (
        <dl className="diag-row__more" data-testid={`diag-row-more-${row.id}`}>
          <dt>{DIAG_CAUSE_LABEL}</dt>
          <dd>{row.cause}</dd>
          <dt>{DIAG_FIX_LABEL}</dt>
          <dd>{row.fix}</dd>
          {since && (
            <>
              <dt>{DIAG_SINCE_LABEL}</dt>
              <dd>{since}</dd>
            </>
          )}
          {row.evidence && Object.keys(row.evidence).length > 0 && (
            <>
              <dt>{DIAG_EVIDENCE_LABEL}</dt>
              <dd>
                <pre className="diag-row__evidence">{JSON.stringify(row.evidence, null, 2)}</pre>
              </dd>
            </>
          )}
        </dl>
      )}
    </li>
  );
}

export function DiagnosticsChecklist({ data, actions, busy, onRefresh, copyBundle }: Props) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const [fallbackText, setFallbackText] = useState<string | null>(null);
  const grouped = useMemo(
    () =>
      (data.groups ?? []).map((g) => ({
        ...g,
        rows: (data.rows ?? []).filter((r) => r.group === g.id),
      })).filter((g) => g.rows.length > 0),
    [data],
  );

  const onCopy = async () => {
    let text = '';
    try {
      text = await copyBundle();
      await navigator.clipboard.writeText(text);
      setCopyState('copied');
      setFallbackText(null);
    } catch {
      setCopyState('failed');
      setFallbackText(text || null);
    }
  };

  return (
    <section className="diag" data-testid="diagnostics-checklist" aria-label={DIAG_TITLE}>
      <div className="diag__head">
        <h3 className="diag__title">{DIAG_TITLE}</h3>
        <span className="diag__counts" data-testid="diag-counts">
          {DIAG_COUNTS_ORDER.filter((s) => (data.counts?.[s] ?? 0) > 0).map((s) => (
            <span key={s} className={`diag-count diag-count--${s}`}>
              <span className={`diag-dot diag-dot--${s}`} aria-hidden /> {data.counts?.[s]} {DIAG_STATE_LABELS[s]}
            </span>
          ))}
        </span>
        <span className="diag__tools">
          <button type="button" className="diag__btn" onClick={onRefresh} data-testid="diag-refresh">
            {DIAG_REFRESH_LABEL}
          </button>
          <button type="button" className="diag__btn" onClick={() => void onCopy()} data-testid="diag-copy">
            {copyState === 'copied' ? DIAG_COPIED_LABEL : DIAG_COPY_LABEL}
          </button>
        </span>
      </div>
      <p className="diag__lead">{DIAG_LEAD}</p>
      {copyState === 'failed' && (
        <div className="diag__fallback" data-testid="diag-copy-failed">
          <p>{DIAG_COPY_FAILED}</p>
          {fallbackText && <textarea readOnly value={fallbackText} rows={6} />}
        </div>
      )}
      {grouped.map((g) => (
        <div key={g.id} className="diag__group" data-testid={`diag-group-${g.id}`}>
          <h4 className="diag__group-title">{g.title}</h4>
          <ul className="diag__rows">
            {g.rows.map((row) => (
              <Row key={row.id} row={row} actions={actions} busy={busy} />
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
