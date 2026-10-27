/**
 * A hidden tab's line lent to Claude (ADR 068 decision 14, approved design `F:\Nova\design\claude-seat\v3`).
 *
 * - `ClaudeLentWords`: what the tab's Level 2 and Time & Sales show while Claude holds their line -- violet, with
 *   Claude's mark, and no button: bringing the tab to the front does not take it back. A right-click on it opens
 *   the one row below.
 * - `ClaudeTakeBackRow`: "Take my Level 2 back from Claude", in the tab's right-click symbol menu and the lent
 *   panes' own. Only that line comes back: Claude stays on, its stop and targets keep resting, and it waits for
 *   another line. A refusal stays on screen in the backend's words.
 */
import { useEffect, useState, type MouseEvent } from 'react';
import { createPortal } from 'react-dom';
import { TriangleAlert } from 'lucide-react';
import { LENT_LINE_RECALL_EVENT } from '../constantGroups/market_ui';
import { takeTabLineBack } from './claudeSeatApi';
import { applyClaudeSeat, useClaudeSeat } from './claudeSeatStore';
import { ClaudeMark } from './ClaudeMark';
import './claudeSeat.css';

export const CLAUDE_TAKE_BACK_LABEL = 'Take my Level 2 back from Claude';

/** The line under the row: what stays as it is. */
export function takeBackHint(held: string | null, holdsShares: boolean): string {
  if (held && holdsShares) {
    return `Claude stays on. Its stop and sell on ${held} keep resting; it waits for another line.`;
  }
  return 'Claude stays on and waits for another line.';
}

export function ClaudeTakeBackRow({ symbol, onDone }: { symbol: string; onDone: () => void }) {
  const { status } = useClaudeSeat();
  const [busy, setBusy] = useState(false);
  const [why, setWhy] = useState<string | null>(null);
  const sym = symbol.toUpperCase();
  if (!status || status.line.from_tab !== sym) return null;
  const held = status.line.symbol;
  const press = async () => {
    setBusy(true);
    setWhy(null);
    try {
      applyClaudeSeat(await takeTabLineBack(sym));
      // The tab's panes ask for their lines now, without waiting on the lines poll.
      window.dispatchEvent(new CustomEvent(LENT_LINE_RECALL_EVENT, { detail: { symbol: sym } }));
      onDone();
    } catch (err) {
      setWhy(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button type="button" role="menuitem" className="symbol-menu__row symbol-menu__row--claude"
        data-testid="claude-take-back" disabled={busy}
        data-why={busy ? 'Waiting for Nova to answer your last press.' : undefined}
        onClick={() => { void press(); }}>
        <span className="symbol-menu__icon symbol-menu__icon--claude" aria-hidden="true"><ClaudeMark size={18} /></span>
        <span className="symbol-menu__text">
          <span className="symbol-menu__label">{CLAUDE_TAKE_BACK_LABEL}</span>
          <span className="symbol-menu__hint">{takeBackHint(held, status.positions.some(p => p.qty > 0))}</span>
        </span>
      </button>
      {why ? (
        <div className="symbol-menu__error" role="alert" data-testid="claude-take-back-error">
          <TriangleAlert size={13} aria-hidden="true" />
          <span>{why}</span>
        </div>
      ) : null}
    </>
  );
}

/** The sentence in parts, "Claude (watching RUNR)" marked, as the approved design draws it. */
export function lentParts(text: string): { text: string; claude: boolean }[] {
  const m = /Claude(?: \([^)]*\))?/.exec(text);
  if (!m) return [{ text, claude: false }];
  return [
    { text: text.slice(0, m.index), claude: false },
    { text: m[0], claude: true },
    { text: text.slice(m.index + m[0].length), claude: false },
  ].filter(p => p.text);
}

/** The lent pane's words; a right-click opens Take my Level 2 back from Claude. */
export function ClaudeLentWords({ symbol, text, testId, className }: {
  symbol: string; text: string; testId: string; className: string;
}) {
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  useEffect(() => {
    if (!menu) return undefined;
    const away = (e: globalThis.MouseEvent) => {
      if (!(e.target as HTMLElement | null)?.closest('[data-testid="claude-lent-menu"]')) setMenu(null);
    };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenu(null); };
    window.addEventListener('mousedown', away);
    window.addEventListener('keydown', esc);
    return () => {
      window.removeEventListener('mousedown', away);
      window.removeEventListener('keydown', esc);
    };
  }, [menu]);
  const open = (e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setMenu({ x: e.clientX, y: e.clientY });
  };
  return (
    <div className={`${className} claude-lent`} data-testid={testId} role="status" onContextMenu={open}>
      <ClaudeMark size={16} />
      <span className="claude-lent__text">{lentParts(text).map((part, i) => (part.claude
        ? <b key={i} className="claude-lent__who">{part.text}</b> : <span key={i}>{part.text}</span>))}</span>
      {/* On the page's body: a pane's overflow never clips it. */}
      {menu ? createPortal(
        <div className="symbol-menu claude-lent-menu" role="menu" data-testid="claude-lent-menu"
          style={{ top: menu.y, left: menu.x }} onContextMenu={e => e.preventDefault()}>
          <div className="symbol-menu__head"><span className="symbol-menu__sym">{symbol.toUpperCase()}</span></div>
          <ClaudeTakeBackRow symbol={symbol} onDone={() => setMenu(null)} />
        </div>,
        document.body,
      ) : null}
    </div>
  );
}
