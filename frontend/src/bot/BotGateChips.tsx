/**
 * Every gate between the bot and a fire, as chips (approved mockup v4): a tick
 * when open, a cross when closed, and the one action that opens a closed gate
 * right on the chip -- unlock the padlock, open a symbol's Level 2, see the
 * read-out, add a symbol, reset the kill switch. The facts are the backend's
 * (bot/gates.py); nothing here decides whether a gate is open.
 */
import { BOTS_GATE_ACTIVATE_TITLE, BOTS_GATE_FIRE_TITLE, BOTS_GATE_MORE } from '../constantGroups/bots_page';
import type { GateAction, GateLine } from './botsPageFormat';

export interface GateHandlers {
  onUnlock: () => void;
  onOpenL2: (symbol: string) => void;
  onReadout: () => void;
  onAddSymbol: () => void;
  onResetKill: () => void;
}

function run(action: GateAction, h: GateHandlers): void {
  switch (action.kind) {
    case 'unlock': h.onUnlock(); break;
    case 'open_l2': if (action.symbol) h.onOpenL2(action.symbol); break;
    case 'readout': h.onReadout(); break;
    case 'add_symbol': h.onAddSymbol(); break;
    case 'reset_kill': h.onResetKill(); break;
    default: break;
  }
}

export function BotGateChips({ gates, handlers }: { gates: GateLine[]; handlers: GateHandlers }) {
  return (
    <ul className="bots-gates" data-testid="bots-gates">
      {gates.map(g => (
        <li
          key={g.id}
          className={`bots-gate ${g.ok ? 'is-ok' : 'is-closed'}${!g.ok && g.stage !== 'activate' ? ' is-fire' : ''}`}
          data-testid={`bots-gate-${g.id}`}
          title={g.stage === 'activate' ? BOTS_GATE_ACTIVATE_TITLE : BOTS_GATE_FIRE_TITLE}
        >
          <span className="bots-gate__mark" aria-hidden="true">{g.ok ? '✓' : '✕'}</span>
          <span className="bots-gate__text">{g.text}</span>
          {g.actions.map((a, i) => (
            <span key={`${a.kind}-${a.symbol ?? i}`} className="bots-gate__act">
              <span aria-hidden="true">{i === 0 ? ' — ' : ', '}</span>
              <button type="button" className="bots-gate__link" data-testid={`bots-gate-action-${a.kind}${a.symbol ? `-${a.symbol}` : ''}`}
                onClick={() => run(a, handlers)}>
                {a.label}
              </button>
            </span>
          ))}
          {g.more > 0 ? <span className="bots-gate__more"> {BOTS_GATE_MORE(g.more)}</span> : null}
        </li>
      ))}
    </ul>
  );
}
