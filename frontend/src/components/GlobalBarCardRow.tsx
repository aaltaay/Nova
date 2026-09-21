/** One label / value row inside a GlobalAppBar card (Day's, TAV, account pill menu). */
interface Props {
  label: string;
  value: string;
  /** P&L tone class (`global-app-bar__tone--*`) or a row modifier. */
  tone?: string;
  title?: string;
  testId?: string;
  empty?: boolean;
}

export function GlobalBarCardRow({ label, value, tone, title, testId, empty }: Props) {
  return (
    <div
      className={`global-app-bar__card-row${empty ? ' is-empty' : ''}`}
      title={title}
      data-testid={testId}
    >
      <span>{label}</span>
      <span className={tone}>{value}</span>
    </div>
  );
}
