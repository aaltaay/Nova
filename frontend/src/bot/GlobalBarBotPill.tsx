/**
 * The Bot switch in the global bar (ADR 044): "● Bot ON · 2 strategies On" or "● Bot OFF" beside the account
 * figures, on every view, with why it is off (or not trading now) on hover. A click opens the Bots page,
 * where the switch is. It shows state only. The sample desk has no bot: no pill.
 */
import { BOTS_PILL_LABEL, BOTS_PILL_TITLE, DESK_BOT_POLL_MS } from '../constants';
import { setNavPage } from '../workspace/navRailStore';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { botHeaderState } from './botHeaderState';
import { useBotSession } from './useBotSession';
import './globalBarBotPill.css';

export function GlobalBarBotPill() {
  const { session } = useBotSession(DESK_BOT_POLL_MS);
  const { traderViewActive, showScannerView } = useWorkspace();
  if (!session) return null;
  const view = botHeaderState(session);

  function open() {
    if (traderViewActive) showScannerView();
    setNavPage('bots');
  }

  return (
    <span className="global-bar-bot-pill-slot" data-testid="global-bar-bot-pill-slot">
      <span className="global-app-bar__sep" aria-hidden />
      <button
        type="button"
        className={`global-bar-bot-pill global-bar-bot-pill--${view.tone}`}
        data-testid="global-bar-bot-pill"
        title={`${view.title} · ${BOTS_PILL_TITLE}`}
        onClick={open}
      >
        <span className="global-bar-bot-pill__dot" aria-hidden="true" />
        <span className="global-bar-bot-pill__label">{BOTS_PILL_LABEL}</span>
        <b className="global-bar-bot-pill__name" data-testid="global-bar-bot-pill-name">{view.name}</b>
        {view.on ? <span className="global-bar-bot-pill__state">· {view.reason ? 'not trading now' : view.detail}</span> : null}
      </button>
    </span>
  );
}
