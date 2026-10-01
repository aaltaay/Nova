/**
 * Every gate between the bot and a trade, as chips (approved mockup v4, ADR 042 C),
 * in two groups: what Activate needs, and what each order still meets. A tick when
 * open, a cross when closed, the chip's hover saying what it checks and why it is
 * closed, and the one action that opens it right on the chip -- unlock the padlock,
 * open a stock's Level 2, set a card to Strategy, add a stock, reset the kill
 * switch. The facts are the backend's (bot/gates.py); nothing here decides.
 */
import {
  BOTS_GATE_MORE,
  BOTS_GATES_ACTIVATE_HEAD,
  BOTS_GATES_ACTIVATE_TIP,
  BOTS_GATES_FIRE_HEAD,
  BOTS_GATES_FIRE_TIP,
} from '../constantGroups/bots_page';
import { tipProps } from '../ux/hoverTip';
import type { GateAction, GateLine } from './botGateWords';

export interface GateHandlers {
  onUnlock: () => void;
  onOpenL2: (symbol: string) => void;
  onShowSetups: () => void;
  onAddSymbol: () => void;
  onResetKill: () => void;
}

function run(action: GateAction, h: GateHandlers): void {
  switch (action.kind) {
    case 'unlock': h.onUnlock(); break;
    case 'open_l2': if (action.symbol) h.onOpenL2(action.symbol); break;
    case 'setups': h.onShowSetups(); break;
    case 'add_symbol': h.onAddSymbol(); break;
    case 'reset_kill': h.onResetKill(); break;
    default: break;
  }
}

function Chip({ g, handlers }: { g: GateLine; handlers: GateHandlers }) {
  return (
    <li
      className={`bots-gate ${g.ok ? 'is-ok' : 'is-closed'}${!g.ok && g.stage !== 'activate' ? ' is-fire' : ''}`}
      data-testid={`bots-gate-${g.id}`}
    >
      <span className="bots-gate__mark" aria-hidden="true">{g.ok ? '✓' : '✕'}</span>
      <span className="bots-gate__text" {...tipProps(g.tip, g.text)}>{g.text}</span>
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
  );
}

export function BotGateChips({ gates, handlers }: { gates: GateLine[]; handlers: GateHandlers }) {
  const activate = gates.filter(g => g.stage === 'activate');
  const fire = gates.filter(g => g.stage !== 'activate');
  return (
    <div className="bots-gategroups" data-testid="bots-gates">
      {activate.length ? (
        <div className="bots-gategroup" data-testid="bots-gates-activate">
          <span className="bots-gategroup__head" {...tipProps(BOTS_GATES_ACTIVATE_TIP, BOTS_GATES_ACTIVATE_HEAD)}>
            {BOTS_GATES_ACTIVATE_HEAD}
          </span>
          <ul className="bots-gates">{activate.map(g => <Chip key={g.id} g={g} handlers={handlers} />)}</ul>
        </div>
      ) : null}
      {fire.length ? (
        <div className="bots-gategroup" data-testid="bots-gates-fire">
          <span className="bots-gategroup__head" {...tipProps(BOTS_GATES_FIRE_TIP, BOTS_GATES_FIRE_HEAD)}>
            {BOTS_GATES_FIRE_HEAD}
          </span>
          <ul className="bots-gates">{fire.map(g => <Chip key={g.id} g={g} handlers={handlers} />)}</ul>
        </div>
      ) : null}
    </div>
  );
}
