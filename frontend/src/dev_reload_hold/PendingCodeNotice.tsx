/**
 * The pending-code notice of the browser development desk (#612): new code is
 * on disk, or the dev server stopped or restarted, and this page keeps running
 * what it loaded until the operator clicks Reload. Later folds it into a chip;
 * nothing applies while it is folded. It never takes keyboard focus, so a hot
 * key pressed while it appears still reaches the desk.
 */
import { useSyncExternalStore, type MouseEvent } from 'react';
import { pendingSummary, type PendingSummary } from './holdModel';
import type { HoldStore } from './installReloadHold';
import './devReloadHold.css';

interface Props {
  store: HoldStore;
  reload: () => void;
}

function headline(s: PendingSummary): string {
  if (s.server === 'down') return 'The dev server stopped. This page keeps running the code it loaded.';
  if (s.restarted) return 'The dev server restarted with the code on disk.';
  if (s.changes) return `New code is on disk (${s.changes} ${s.changes === 1 ? 'change' : 'changes'}).`;
  return 'New code is on disk.';
}

function detail(s: PendingSummary): string[] {
  const lines: string[] = [];
  if (s.files.length) lines.push(`Changed: ${s.files.join(', ')}${s.moreFiles ? ` and ${s.moreFiles} more` : ''}.`);
  if (s.runningHead && s.diskHead && s.runningHead !== s.diskHead) {
    lines.push(`This page runs ${s.runningHead}; the checkout is at ${s.diskHead}.`);
  }
  lines.push(
    s.server === 'down'
      ? 'Nothing changes on this page until you click Reload.'
      : 'Nothing changes on this page until you click Reload: route, symbol and charts stay as they are.',
  );
  return lines;
}

export function PendingCodeNotice({ store, reload }: Props) {
  const view = useSyncExternalStore(store.subscribe, store.get, store.get);
  const summary = pendingSummary(view);
  if (!summary) return null;
  const preventFocus = (e: MouseEvent) => e.preventDefault();
  if (view.folded) {
    return (
      <button
        type="button"
        className="nova-dev-hold-chip"
        data-testid="dev-reload-chip"
        onMouseDown={preventFocus}
        onClick={() => store.fold(false)}
        title="New code waits for your Reload"
      >
        Code pending
      </button>
    );
  }
  return (
    <div className="nova-dev-hold" role="status" data-testid="dev-reload-notice" data-server={summary.server}>
      <div className="nova-dev-hold__text">
        <strong>{headline(summary)}</strong>
        {detail(summary).map((line) => (
          <span key={line} className="nova-dev-hold__line">
            {line}
          </span>
        ))}
      </div>
      <div className="nova-dev-hold__actions">
        <button type="button" className="nova-dev-hold__btn" onMouseDown={preventFocus} onClick={() => store.fold(true)}>
          Later
        </button>
        <button
          type="button"
          className="nova-dev-hold__btn nova-dev-hold__btn--primary"
          onMouseDown={preventFocus}
          onClick={reload}
        >
          Reload
        </button>
      </div>
    </div>
  );
}
