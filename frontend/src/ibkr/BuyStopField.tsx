/**
 * The short's required Buy stop (ADR 048: every short goes out with a protective buy stop over its entry,
 * which takes effect when the short fills). It starts at the venue's Settings > Trade offset over the limit
 * and says what the short loses at it.
 */
import {
  SHORT_STOP_NOTE_OVER,
  SHORT_TICKET_BUY_STOP_LABEL,
  SHORT_TICKET_REQUIRED,
} from '../constantGroups/short_ticket';
import { riskAtStop } from './shortTicketModel';

interface Props {
  value: string;
  limit: string;
  orderQty: string;
  disabled: boolean;
  why: string | null | undefined;
  /** Why the stop as typed cannot go out (missing, or not over the limit); null when it can. */
  refusal: string | null;
  onChange: (next: string) => void;
}

export function BuyStopField({ value, limit, orderQty, disabled, why, refusal, onChange }: Props) {
  const risk = riskAtStop(limit, value, orderQty);
  return (
    <div className="mot-field mot-field--price mot-field--buy-stop">
      <label className="mot-field__k" htmlFor="manual-order-buy-stop">
        {SHORT_TICKET_BUY_STOP_LABEL}
      </label>
      <input
        id="manual-order-buy-stop"
        className={`manual-order-price${refusal ? ' is-refused' : ''}`}
        type="number"
        min="0"
        step="0.01"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        data-why={why ?? undefined}
        aria-invalid={refusal ? true : undefined}
        data-testid="manual-order-buy-stop"
      />
      <span className="mot-field__note" data-testid="manual-order-buy-stop-note">
        {refusal ?? (risk != null ? SHORT_STOP_NOTE_OVER(risk.toFixed(2)) : '')}
      </span>
      <span className="mot-required">{SHORT_TICKET_REQUIRED}</span>
    </div>
  );
}
