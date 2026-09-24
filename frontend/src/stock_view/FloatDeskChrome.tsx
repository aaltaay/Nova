/**
 * Thin chrome for pop-out (float) trader windows — distinguishable from the
 * parent desk. No GlobalAppBar / Bot Autonomy / Paper-Live-Sim.
 */
import { TRADER_TAB_DOCK_ARIA, TRADER_TAB_DOCK_LABEL, TRADER_TAB_DOCK_TITLE } from '../constants';
import { useWorkspace } from '../workspace/WorkspaceContext';

export function FloatDeskChrome() {
  const {
    activeTraderSymbol,
    requestDockTraderTab,
    traderDeskRole,
    traderMoveLocks,
  } = useWorkspace();
  // A sample pop-out (#449) cannot dock back: the button stays, locked, saying why.
  const dockWhy = traderMoveLocks?.dock ?? null;

  if (traderDeskRole !== 'float') return null;
  const sym = (activeTraderSymbol || '').trim().toUpperCase();

  return (
    <div className="float-desk-chrome" data-testid="float-desk-chrome">
      <div className="float-desk-chrome__left">
        <span className="float-desk-chrome__badge">Pop-out</span>
        {sym ? <strong className="float-desk-chrome__symbol">{sym}</strong> : null}
      </div>
      {sym ? (
        <button
          type="button"
          className="float-desk-chrome__dock"
          title={dockWhy ? '' : TRADER_TAB_DOCK_TITLE}
          aria-label={`${TRADER_TAB_DOCK_ARIA} (${sym})`}
          data-testid="float-desk-dock"
          disabled={Boolean(dockWhy)}
          data-why={dockWhy ?? undefined}
          onClick={() => { if (!dockWhy) requestDockTraderTab(sym); }}
        >
          {TRADER_TAB_DOCK_LABEL}
        </button>
      ) : null}
    </div>
  );
}
