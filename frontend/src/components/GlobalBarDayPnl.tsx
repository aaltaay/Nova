/**
 * "P/L: +$12.34 +0.12% | Unrealized P/L: +$5.00 ▾" -- the first control of the
 * compact account cluster -- and its card: Unrealized P/L at the bid, Open P&L
 * at the last, Day's P&L, Day's Realized P&L, plus Fees today on the practice
 * venues. The card opens under this button, never at the cluster's right edge.
 * Numbers arrive as HeaderAccountFigures with each account poll (nothing here
 * runs a timer), so the button does not know whether IBKR or Nova's practice
 * ledger is behind them.
 */
import {
  GLOBAL_BAR_CARD_DAY_PNL,
  GLOBAL_BAR_CARD_OPEN_PNL,
  GLOBAL_BAR_CARD_REALIZED_PNL,
  GLOBAL_BAR_CARD_UNREALIZED_PNL,
  GLOBAL_BAR_DAY_CARD_ARIA,
  GLOBAL_BAR_DAY_PNL_LABEL,
  GLOBAL_BAR_UNREALIZED_LABEL,
  GLOBAL_BAR_UNREALIZED_TITLE,
} from '../constantGroups/global_bar';
import { PRACTICE_CARD_FEES_LABEL } from '../constantGroups/practice';
import { GlobalBarCardRow } from './GlobalBarCardRow';
import { GlobalBarMenuAnchor } from './GlobalBarMenuAnchor';
import { formatSignedMoney, formatSignedPercent, pnlToneClass } from './globalBarMoney';
import { dayPnlPercent, headerMoney, type HeaderAccountFigures } from './headerAccountFigures';

interface ButtonProps {
  figures: HeaderAccountFigures;
  open: boolean;
  cardId: string;
  title: string;
  onToggle: () => void;
  onHover: () => void;
}

export function DayPnlButton({ figures, open, cardId, title, onToggle, onHover }: ButtonProps) {
  const pct = dayPnlPercent(figures.dayPnl, figures.netLiquidation);
  const tone = pnlToneClass(figures.dayPnl);
  const openTone = pnlToneClass(figures.unrealizedAtBid);
  const button = (
    <button
      type="button"
      className="global-app-bar__metric-btn global-app-bar__metric--day"
      aria-expanded={open}
      aria-controls={cardId}
      title={title}
      data-testid="global-bar-account-trigger"
      onClick={onToggle}
      onMouseEnter={onHover}
    >
      <label>{GLOBAL_BAR_DAY_PNL_LABEL}</label>
      <span className={`global-app-bar__metric-value ${tone}`}>{formatSignedMoney(figures.dayPnl)}</span>
      {pct != null && (
        <span className={`global-app-bar__pct ${tone}`} data-testid="global-bar-day-pct">
          {formatSignedPercent(pct)}
        </span>
      )}
      <span className="global-app-bar__metric-sub" title={GLOBAL_BAR_UNREALIZED_TITLE}>
        <label>{GLOBAL_BAR_UNREALIZED_LABEL}</label>
        <span className={`global-app-bar__metric-value ${openTone}`} data-testid="global-bar-unrealized">
          {formatSignedMoney(figures.unrealizedAtBid)}
        </span>
      </span>
      <span className="global-app-bar__caret" aria-hidden>
        {open ? '▴' : '▾'}
      </span>
    </button>
  );
  return (
    <GlobalBarMenuAnchor open={open} cardId={cardId} button={button}>
      <DayPnlCard figures={figures} />
    </GlobalBarMenuAnchor>
  );
}

export function DayPnlCard({ figures }: { figures: HeaderAccountFigures }) {
  return (
    <div
      className="global-app-bar__card"
      role="dialog"
      aria-label={GLOBAL_BAR_DAY_CARD_ARIA}
      data-testid="global-bar-day-card"
    >
      <GlobalBarCardRow
        label={GLOBAL_BAR_CARD_UNREALIZED_PNL}
        value={formatSignedMoney(figures.unrealizedAtBid)}
        tone={pnlToneClass(figures.unrealizedAtBid)}
      />
      <GlobalBarCardRow
        label={GLOBAL_BAR_CARD_OPEN_PNL}
        value={formatSignedMoney(figures.openPnl)}
        tone={pnlToneClass(figures.openPnl)}
      />
      <GlobalBarCardRow
        label={GLOBAL_BAR_CARD_DAY_PNL}
        value={formatSignedMoney(figures.dayPnl)}
        tone={pnlToneClass(figures.dayPnl)}
      />
      <GlobalBarCardRow
        label={GLOBAL_BAR_CARD_REALIZED_PNL}
        value={formatSignedMoney(figures.realizedPnl)}
        tone={pnlToneClass(figures.realizedPnl)}
      />
      {figures.source === 'practice' && (
        <GlobalBarCardRow
          label={PRACTICE_CARD_FEES_LABEL}
          value={headerMoney(figures.feesToday)}
          testId="global-bar-card-fees"
        />
      )}
    </div>
  );
}
