/**
 * Middle bottom -- Ledger: the one primary button on the page (Reset
 * practice account, Paper only, through the existing confirm + POST), the
 * starting cash beside it, and the history rows -- fills with their `est`
 * chip, source, commission and fees, the 04:00 ET rollovers, the starting
 * cash and the resets -- with the balance after each.
 */
import { useMemo, useState } from 'react';
import {
  ACCOUNT_LEDGER_COL_ACTION,
  ACCOUNT_LEDGER_COL_AMOUNT,
  ACCOUNT_LEDGER_COL_BALANCE,
  ACCOUNT_LEDGER_COL_TIME,
  ACCOUNT_LEDGER_COL_TYPE,
  ACCOUNT_LEDGER_COMM,
  ACCOUNT_LEDGER_EMPTY,
  ACCOUNT_LEDGER_FEES,
  ACCOUNT_LEDGER_FILE,
  ACCOUNT_LEDGER_ROLLOVER_ACTION,
  ACCOUNT_LEDGER_ROLLOVER_TAG,
  ACCOUNT_LEDGER_START_ACTION,
  ACCOUNT_LEDGER_TYPE_FILL,
  ACCOUNT_LEDGER_TYPE_RESET,
  ACCOUNT_LEDGER_TYPE_ROLLOVER,
  ACCOUNT_LEDGER_TYPE_START,
  ACCOUNT_RESET_BUTTON,
  ACCOUNT_RESET_HINT_PAPER,
  ACCOUNT_RESET_HINT_SIM,
  ACCOUNT_STARTING_CASH,
  ACCOUNT_WARNINGS_PREFIX,
  accountLedgerFoot,
  accountLedgerResetAction,
  accountLedgerTitle,
} from '../constantGroups/account_page';
import type { DeskVenue } from '../constantGroups/desk_venue';
import {
  PRACTICE_RESET_CONFIRM_LABEL,
  PRACTICE_RESET_FAILED,
  practiceResetBusyWhy,
  practiceResetConfirmMessage,
  practiceResetConfirmTitle,
  practiceResetDone,
} from '../constantGroups/practice';
import { formatSignedMoney } from '../components/globalBarMoney';
import { resetPracticeAccount } from '../practice/practiceAccountResource';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import { confirmApp } from '../ux';
import { EstChip, Money, PanelHead, etDateTime, etDateTimeIso } from './accountBits';
import { sourceKind, sourceLabel } from './accountFigures';
import { invalidateAccountHistory } from './accountHistoryResource';
import type { PracticeHistory } from './accountHistoryTypes';
import { ledgerRows, type LedgerRow } from './accountLedgerRows';

interface Props {
  venue: DeskVenue;
  history: PracticeHistory | null;
  absence: string | null;
  accountId: string | null;
  startingCash: number | null;
}

function ResetButton({ startingCash }: { startingCash: number | null }) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);
  const reset = async () => {
    const confirmed = await confirmApp({
      title: practiceResetConfirmTitle('paper'),
      message: practiceResetConfirmMessage('paper', null),
      confirmLabel: PRACTICE_RESET_CONFIRM_LABEL,
      tone: 'warning',
    });
    if (!confirmed) return;
    setBusy(true);
    setNotice(null);
    try {
      const account = await resetPracticeAccount('paper', null);
      invalidateAccountHistory('paper');
      setNotice({ tone: 'ok', text: practiceResetDone('paper', formatMoney(account.cash)) });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setNotice({ tone: 'error', text: `${PRACTICE_RESET_FAILED}: ${detail}` });
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button type="button" className="acct-btn-primary" disabled={busy} data-why={busy ? practiceResetBusyWhy('paper') : undefined}
        data-testid="account-reset-button" onClick={() => void reset()}>
        {ACCOUNT_RESET_BUTTON}
      </button>
      <div className="acct-field"><span className="acct-row__k">{ACCOUNT_STARTING_CASH}</span><span className="acct-num">{formatMoney(startingCash)}</span></div>
      <span className="acct-hint">{ACCOUNT_RESET_HINT_PAPER}</span>
      {notice && (
        <span className={`acct-hint acct-notice--${notice.tone}`} role={notice.tone === 'error' ? 'alert' : 'status'} data-testid="account-reset-notice">
          {notice.text}
        </span>
      )}
    </>
  );
}

const TYPE_LABELS: Record<LedgerRow['kind'], string> = {
  fill: ACCOUNT_LEDGER_TYPE_FILL,
  rollover: ACCOUNT_LEDGER_TYPE_ROLLOVER,
  start: ACCOUNT_LEDGER_TYPE_START,
  reset: ACCOUNT_LEDGER_TYPE_RESET,
};

/** The Action cell as it reads: a fill leads with its side and symbol, a system row with its words. */
function actionSortText(row: LedgerRow): string {
  if (row.kind === 'fill' && row.fill) return `${row.fill.side} ${row.fill.symbol}`;
  if (row.kind === 'rollover') return ACCOUNT_LEDGER_ROLLOVER_ACTION;
  if (row.kind === 'start') return ACCOUNT_LEDGER_START_ACTION;
  return accountLedgerResetAction(row.archive?.file ?? '—', formatSignedMoney(row.archive?.realized));
}

const COLUMNS: SortColumns<LedgerRow> = {
  type: r => TYPE_LABELS[r.kind],
  action: actionSortText,
  time: r => r.ts,
  amount: r => r.amount,
  balance: r => r.balance,
};

function RowCells({ row }: { row: LedgerRow }) {
  if (row.kind === 'fill' && row.fill) {
    const f = row.fill;
    const kind = sourceKind(f.source);
    return (
      <>
        <td>{ACCOUNT_LEDGER_TYPE_FILL}</td>
        <td>
          <span className={f.side === 'BUY' ? 'acct-side--buy' : 'acct-side--sell'}>{f.side}</span> {formatShareQty(f.qty)} {f.symbol} @ {f.price.toFixed(2)}<EstChip />
          {' · '}<span className={`acct-src${kind === 'bot' ? ' is-bot' : ''}`}>{sourceLabel(f.source, f.bot_id)}</span>
          {(f.commission || f.fees) ? (
            <span className="acct-muted"> · {ACCOUNT_LEDGER_COMM} {formatMoney(f.commission)}{f.fees ? ` · ${ACCOUNT_LEDGER_FEES} ${formatMoney(f.fees)}` : ''}</span>
          ) : null}
        </td>
        <td className="acct-num">{etDateTime(row.ts)}</td>
        <td className="r"><Money value={row.amount} signed kind="cash" /></td>
        <td className="r">{row.balance == null ? <span className="acct-muted">—</span> : <Money value={row.balance} />}</td>
      </>
    );
  }
  const action = row.kind === 'rollover'
    ? <>{ACCOUNT_LEDGER_ROLLOVER_ACTION} · <span className="acct-tag">{ACCOUNT_LEDGER_ROLLOVER_TAG}</span></>
    : row.kind === 'start'
      ? ACCOUNT_LEDGER_START_ACTION
      : accountLedgerResetAction(row.archive?.file ?? '—', formatSignedMoney(row.archive?.realized));
  const type = row.kind === 'rollover' ? ACCOUNT_LEDGER_TYPE_ROLLOVER : row.kind === 'start' ? ACCOUNT_LEDGER_TYPE_START : ACCOUNT_LEDGER_TYPE_RESET;
  return (
    <>
      <td>{type}</td>
      <td>{action}</td>
      <td className="acct-num">{etDateTime(row.ts)}</td>
      <td className="r">{row.amount == null ? '—' : <Money value={row.amount} signed kind="cash" />}</td>
      <td className="r">{row.balance == null ? '—' : <Money value={row.balance} />}</td>
    </>
  );
}

export function LedgerPanel({ venue, history, absence, accountId, startingCash }: Props) {
  const rows = useMemo(() => (history ? ledgerRows(history) : []), [history]);
  const { rows: sorted, sort, onSort } = useTableSort('account.ledger', rows, COLUMNS);
  return (
    <section className="acct-panel acct-panel--ledger" data-testid="account-ledger" aria-label={accountLedgerTitle(accountId)}>
      <PanelHead title={accountLedgerTitle(accountId)} />
      {venue !== 'live' && (
        <div className="acct-reset-bar" data-testid="account-reset-bar">
          {venue === 'paper' ? <ResetButton startingCash={startingCash} /> : <span className="acct-hint">{ACCOUNT_RESET_HINT_SIM}</span>}
        </div>
      )}
      {!history ? (
        <div className="acct-absent" data-testid="account-ledger-absent">{absence}</div>
      ) : (
        <>
          <div className="acct-scroll">
            <table className="acct-table" data-testid="account-ledger-table">
              <thead>
                <tr>
                  <SortTh col="type" sort={sort} onSort={onSort}>{ACCOUNT_LEDGER_COL_TYPE}</SortTh>
                  <SortTh col="action" sort={sort} onSort={onSort}>{ACCOUNT_LEDGER_COL_ACTION}</SortTh>
                  <SortTh col="time" sort={sort} onSort={onSort}>{ACCOUNT_LEDGER_COL_TIME}</SortTh>
                  <SortTh col="amount" sort={sort} onSort={onSort} className="r">{ACCOUNT_LEDGER_COL_AMOUNT}</SortTh>
                  <SortTh col="balance" sort={sort} onSort={onSort} className="r">{ACCOUNT_LEDGER_COL_BALANCE}</SortTh>
                </tr>
              </thead>
              <tbody>
                {sorted.length === 0 ? (
                  <tr><td colSpan={5} className="acct-muted">{ACCOUNT_LEDGER_EMPTY}</td></tr>
                ) : sorted.map((row) => (
                  <tr key={row.key} className={row.kind === 'fill' ? '' : 'acct-table__sys'} data-testid={`account-ledger-row-${row.kind}`}>
                    <RowCells row={row} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="acct-foot" data-testid="account-ledger-foot">
            {accountLedgerFoot(ACCOUNT_LEDGER_FILE[history.venue], history.schema_version, etDateTimeIso(history.ledger_opened_at), history.archives.length)}
            {history.warnings.length > 0 && <> {ACCOUNT_WARNINGS_PREFIX} {history.warnings.join('; ')}</>}
          </p>
        </>
      )}
    </section>
  );
}
