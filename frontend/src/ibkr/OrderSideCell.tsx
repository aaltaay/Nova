import { tipProps } from '../ux/hoverTip';
import { orderSideWords, positionSideWords } from './orderSide';
import type { IbkrOrder, IbkrPosition } from './types';
import './orderSide.css';

/** The Side cell of the Working and Closed order tables (`orderSideWords`, ADR 048). */
export function OrderSideTd({ order }: { order: IbkrOrder }) {
  const words = orderSideWords(order);
  return (
    <td
      className="ibkr-col--text ibkr-col--side"
      data-testid="ibkr-order-side"
      data-side-tone={words.tone}
      {...tipProps(words.tip, words.label)}
    >
      <span className={`ibkr-side-tag ibkr-side-tag--${words.tone}`}>{words.tag}</span>
      {' · '}
      {words.action}
      {words.effect ? <span className="ibkr-side-effect"> · {words.effect}</span> : null}
    </td>
  );
}

/** The Side cell of the Positions table: LONG "shares you own" or SHORT "borrowed · buy back to cover". */
export function PositionSideTd({ position }: { position: IbkrPosition }) {
  const words = positionSideWords(position);
  return (
    <td
      className="ibkr-col--text ibkr-col--side"
      data-testid="ibkr-position-side"
      data-side-tone={words.tone}
      {...tipProps(words.tip, words.tag)}
    >
      <span className={`ibkr-side-tag ibkr-side-tag--${words.tone}`}>{words.tag}</span>
      {words.note ? <span className="ibkr-side-effect"> {words.note}</span> : null}
    </td>
  );
}
