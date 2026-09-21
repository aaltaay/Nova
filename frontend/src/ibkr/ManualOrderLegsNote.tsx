/**
 * #91 — one line under the ticket fields saying what the operator's default
 * TP / SL will do to this order: attach, stand aside (exit, Sim), or refuse it.
 */
interface Props {
  note: string | null;
  blocked: boolean;
}

export function ManualOrderLegsNote({ note, blocked }: Props) {
  if (!note) return null;
  return (
    <span
      className="manual-order-lock-note"
      data-testid="ticket-legs-note"
      data-blocked={blocked ? 'true' : 'false'}
    >
      {note}
    </span>
  );
}
