/**
 * Hot strip shown only while the desk venue is Paper -- Nova's practice account,
 * fake money on the live feed, never an IBKR paper account (ADR 020).
 * Sim shows none (operator decision, 2026-09-20): the venue already reads from the
 * header's DESK SIM chip and the active Sim pill, and a full-width strip on every
 * Sim tab was noise. A Sim tab's replay state has its own strip (SimReplayTargetNotice).
 */
import { PAPER_TRADING_BANNER_TEXT } from '../constants';
import type { IbkrMode } from './types';
import './paperTradingBanner.css';

interface Props {
  mode: IbkrMode;
}

export function PaperTradingBanner({ mode }: Props) {
  if (mode !== 'paper') return null;
  return (
    <div
      className="paper-trading-banner"
      role="status"
      data-testid="paper-trading-banner"
    >
      {PAPER_TRADING_BANNER_TEXT}
    </div>
  );
}
