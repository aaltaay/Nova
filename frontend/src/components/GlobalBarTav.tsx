/**
 * "TAV: $100,000.00 ▾" -- Total Account Value (NetLiquidation) -- and its card:
 * TAV, Cash, Buying Power, Excess Liquidity (IBKR only, omitted when IBKR does
 * not report it), Gross Position Value; the practice venues add Starting cash,
 * and Sim adds the replay its scratch ledger belongs to (ADR 019 / 020).
 */
import {
  GLOBAL_BAR_CARD_BP,
  GLOBAL_BAR_CARD_CASH,
  GLOBAL_BAR_CARD_EXCESS_LIQUIDITY,
  GLOBAL_BAR_CARD_GPV,
  GLOBAL_BAR_CARD_TAV,
  GLOBAL_BAR_TAV_CARD_ARIA,
  GLOBAL_BAR_TAV_LABEL,
} from '../constantGroups/global_bar';
import {
  PRACTICE_CARD_REPLAY_LABEL,
  PRACTICE_CARD_STARTING_CASH_LABEL,
  PRACTICE_NO_REPLAY,
  PRACTICE_REPLAY_KEY_TITLE,
} from '../constantGroups/practice';
import { GlobalBarCardRow } from './GlobalBarCardRow';
import { headerMoney, type HeaderAccountFigures } from './headerAccountFigures';

interface ButtonProps {
  figures: HeaderAccountFigures;
  open: boolean;
  cardId: string;
  title: string;
  onToggle: () => void;
  onHover: () => void;
}

export function TavButton({ figures, open, cardId, title, onToggle, onHover }: ButtonProps) {
  return (
    <button
      type="button"
      className="global-app-bar__metric-btn global-app-bar__metric--tav"
      aria-expanded={open}
      aria-controls={cardId}
      title={title}
      data-testid="global-bar-tav-trigger"
      onClick={onToggle}
      onMouseEnter={onHover}
    >
      <label>{GLOBAL_BAR_TAV_LABEL}</label>
      <span className="global-app-bar__metric-value">{headerMoney(figures.netLiquidation)}</span>
      <span className="global-app-bar__caret" aria-hidden>
        {open ? '▴' : '▾'}
      </span>
    </button>
  );
}

export function TavCard({ figures }: { figures: HeaderAccountFigures }) {
  const practice = figures.source === 'practice';
  return (
    <div
      className="global-app-bar__card"
      role="dialog"
      aria-label={GLOBAL_BAR_TAV_CARD_ARIA}
      data-testid="global-bar-tav-card"
    >
      <GlobalBarCardRow label={GLOBAL_BAR_CARD_TAV} value={headerMoney(figures.netLiquidation)} />
      <GlobalBarCardRow label={GLOBAL_BAR_CARD_CASH} value={headerMoney(figures.cash)} />
      <GlobalBarCardRow label={GLOBAL_BAR_CARD_BP} value={headerMoney(figures.buyingPower)} />
      {figures.source === 'ibkr' && figures.excessLiquidity != null && (
        <GlobalBarCardRow
          label={GLOBAL_BAR_CARD_EXCESS_LIQUIDITY}
          value={headerMoney(figures.excessLiquidity)}
          testId="global-bar-card-excess"
        />
      )}
      <GlobalBarCardRow label={GLOBAL_BAR_CARD_GPV} value={headerMoney(figures.grossPositionValue)} />
      {practice && (
        <GlobalBarCardRow
          label={PRACTICE_CARD_STARTING_CASH_LABEL}
          value={headerMoney(figures.startingCash)}
          testId="global-bar-card-starting-cash"
        />
      )}
      {figures.replayKey != null && (
        <GlobalBarCardRow
          label={PRACTICE_CARD_REPLAY_LABEL}
          value={figures.replayKey || PRACTICE_NO_REPLAY}
          title={PRACTICE_REPLAY_KEY_TITLE}
          empty={!figures.replayKey}
          testId="global-bar-card-replay"
        />
      )}
    </div>
  );
}
