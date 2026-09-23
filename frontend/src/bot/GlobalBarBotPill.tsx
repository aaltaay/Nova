/**
 * The bot in the global bar (approved mockup v4): "● Bot  L2 First pullback ·
 * Not active" beside the account figures, on every view. A click opens the
 * Bots page. It shows state only -- the level and Activate live on the page's
 * hero and in the Trader rail card. The sample desk has no bot: no pill.
 */
import { BOTS_PILL_LABEL, BOTS_PILL_TITLE, DESK_BOT_POLL_MS } from '../constants';
import { botArmDisplayState } from '../ibkr/tradingAllowed';
import { useDeskTradingAllowed } from '../ibkr/useDeskTradingAllowed';
import { setNavPage } from '../workspace/navRailStore';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { botHeaderState } from './botHeaderState';
import { useBotSession } from './useBotSession';
import './globalBarBotPill.css';

export function GlobalBarBotPill() {
  const { session } = useBotSession(DESK_BOT_POLL_MS);
  const gate = useDeskTradingAllowed();
  const { traderViewActive, showScannerView } = useWorkspace();
  if (!session) return null;
  const view = botHeaderState(session, botArmDisplayState(Boolean(session.armed), gate).looksActive);

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
        {view.level ? <b className="global-bar-bot-pill__level">{view.level}</b> : null}
        <b className="global-bar-bot-pill__name">{view.name}</b>
        {view.state ? <span className="global-bar-bot-pill__state">· {view.state}</span> : null}
      </button>
    </span>
  );
}
