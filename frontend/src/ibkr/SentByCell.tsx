import { tipProps } from '../ux/hoverTip';
import { orderSentBy, SENT_BY_TITLE } from './orderSentBy';
import type { IbkrOrder } from './types';

/** The "Sent by" cell of the Working and Closed order tables (`orderSentBy`). */
export function SentByTd({ order }: { order: IbkrOrder }) {
  const by = orderSentBy(order);
  return (
    <td
      className={`ibkr-col--text ibkr-col--sent-by ibkr-sent-by ibkr-sent-by--${by.tone}`}
      data-testid="ibkr-sent-by"
      data-tone={by.tone}
      {...tipProps(by.tip, by.label === '—' ? SENT_BY_TITLE : by.label)}
    >
      {by.label}
    </td>
  );
}
