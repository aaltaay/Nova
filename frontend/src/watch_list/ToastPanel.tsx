/**
 * The Hot list tab's toast panel (ADR 044 amendment, operator ask 2026-10-12): the trading window toasts come in,
 * and today's toasts scored -- per kind, how many, how many were higher five minutes later and the median move --
 * with what the gate held back and why. The scores are Nova's own reading of the 1-minute bars (toastScores.ts),
 * a score and not a fill. Nothing here places an order.
 */
import { useEffect, useState } from 'react';
import { fmtPct, pctToneClass } from '../utils/quoteFormat';
import { tipProps } from '../ux/hoverTip';
import type { HeldReason } from './toastGate';
import { summarizeToasts, useToastScores } from './toastScores';
import { resetToastWindow, saveToastWindow, useToastWindow } from './toastWindow';
import {
  WATCH_TOAST_HELD_LABELS,
  WATCH_TOAST_HELD_TIP,
  WATCH_TOAST_KIND_LABELS,
  WATCH_TOAST_SCORES_EMPTY,
  WATCH_TOAST_SCORES_TIP,
  WATCH_TOAST_SCORES_TITLE,
  WATCH_TOAST_WINDOW_DEFAULT,
  WATCH_TOAST_WINDOW_ET,
  WATCH_TOAST_WINDOW_LABEL,
  WATCH_TOAST_WINDOW_RESET,
  WATCH_TOAST_WINDOW_TIP,
  WATCH_TOAST_WINDOW_TO,
  watchToastHeldLine,
} from './watchListConstants';

const HELD_ORDER: readonly HeldReason[] = ['running_up', 'auto_star', 'forming', 'quiet', 'outside_window'];

function WindowSetting() {
  const saved = useToastWindow();
  const [draft, setDraft] = useState(saved);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setDraft(saved); setError(null); }, [saved]);
  const change = (part: 'start' | 'end', value: string) => {
    const next = { ...draft, [part]: value };
    setDraft(next);
    setError(saveToastWindow(next));
  };
  const isDefault = saved.start === WATCH_TOAST_WINDOW_DEFAULT.start && saved.end === WATCH_TOAST_WINDOW_DEFAULT.end;
  return (
    <div className="watch-list__toast-window" data-testid="watch-toast-window" {...tipProps(WATCH_TOAST_WINDOW_TIP)}>
      <span className="watch-list__toast-label">{WATCH_TOAST_WINDOW_LABEL}</span>
      <input type="time" step={300} value={draft.start} aria-label="Toasts from (ET)" aria-invalid={error !== null}
        data-testid="watch-toast-window-start" onChange={e => change('start', e.target.value)} />
      <span>{WATCH_TOAST_WINDOW_TO}</span>
      <input type="time" step={300} value={draft.end} aria-label="Toasts until (ET)" aria-invalid={error !== null}
        data-testid="watch-toast-window-end" onChange={e => change('end', e.target.value)} />
      <span className="na-muted">{WATCH_TOAST_WINDOW_ET}</span>
      {isDefault ? null : (
        <button type="button" data-testid="watch-toast-window-reset" onClick={() => resetToastWindow()}>
          {WATCH_TOAST_WINDOW_RESET}
        </button>
      )}
      {error ? <span className="watch-list__invalid" role="alert">{error}</span> : null}
    </div>
  );
}

function Scores() {
  const doc = useToastScores();
  const rows = summarizeToasts(doc);
  const held = HELD_ORDER.flatMap(reason => {
    const n = doc.held[reason] ?? 0;
    return n > 0 ? [`${n} ${WATCH_TOAST_HELD_LABELS[reason]}`] : [];
  });
  return (
    <div className="watch-list__toast-scores" data-testid="watch-toast-scores">
      <span className="watch-list__toast-label" {...tipProps(WATCH_TOAST_SCORES_TIP, WATCH_TOAST_SCORES_TITLE)}>
        {WATCH_TOAST_SCORES_TITLE}
      </span>
      {rows.length === 0 ? <span className="na-muted">{WATCH_TOAST_SCORES_EMPTY}</span> : (
        <table className="watch-list__toast-table">
          <thead>
            <tr>
              <th>Kind</th>
              <th className="num">Toasts</th>
              <th className="num" title="Toasts whose five minutes Nova has read">Scored</th>
              <th className="num" title="Scored toasts whose price was higher five minutes later">Higher 5 min later</th>
              <th className="num" title="The middle move five minutes later, of the scored toasts">Median move</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.kind} data-testid={`watch-toast-score-${row.kind}`}>
                <td>{WATCH_TOAST_KIND_LABELS[row.kind] ?? row.kind}</td>
                <td className="num">{row.toasts}</td>
                <td className="num">{row.scored}</td>
                <td className="num">{row.scored ? `${row.higher} of ${row.scored}` : '—'}</td>
                <td className={`num ${pctToneClass(row.medianMove)}`}>{fmtPct(row.medianMove, '—')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {held.length ? (
        <span className="na-muted" data-testid="watch-toast-held" {...tipProps(WATCH_TOAST_HELD_TIP)}>
          {watchToastHeldLine(held)}
        </span>
      ) : null}
    </div>
  );
}

export function ToastPanel() {
  return (
    <section className="watch-list__toasts" data-testid="watch-toast-panel">
      <WindowSetting />
      <Scores />
    </section>
  );
}
