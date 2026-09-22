/**
 * Left column -- Webull's full-height "Account Details" side column bent to
 * what Nova can state: TAV with the eye, the event-marked equity curve, the
 * two cards, the rows that add up to Day's P&L, the cash-vs-positions donut
 * and the Risk Level block driven by Nova's own breakers.
 */
import {
  ACCOUNT_CARD_CASH,
  ACCOUNT_CARD_FLAT,
  ACCOUNT_CARD_POSITIONS,
  ACCOUNT_CASH_SUB,
  ACCOUNT_DETAILS_TITLE,
  ACCOUNT_DONUT_CENTER,
  ACCOUNT_DONUT_DROPDOWN,
  ACCOUNT_DONUT_TITLE,
  ACCOUNT_EXCESS_NA_PRACTICE,
  ACCOUNT_EYE_HIDE,
  ACCOUNT_EYE_SHOW,
  ACCOUNT_HISTORY_RANGES,
  ACCOUNT_LEGEND_CASH,
  ACCOUNT_LEGEND_POSITIONS,
  ACCOUNT_LEGEND_SHORT,
  ACCOUNT_LEGEND_SHORT_NONE,
  ACCOUNT_LEGEND_SHORT_NONE_LIVE,
  ACCOUNT_LEGEND_UNSETTLED,
  ACCOUNT_LEGEND_UNSETTLED_LIVE,
  ACCOUNT_LEGEND_UNSETTLED_NA,
  ACCOUNT_LIVE_NO_LEDGER,
  ACCOUNT_RISK_BREAKERS,
  ACCOUNT_RISK_BREAKERS_NOT_EXPOSED,
  ACCOUNT_RISK_DAY_LOCK,
  ACCOUNT_RISK_BOT_ORDER_SIZE,
  ACCOUNT_RISK_BOT_ORDER_SIZE_NONE,
  ACCOUNT_RISK_LARGEST_POSITION,
  ACCOUNT_RISK_LOCKED,
  ACCOUNT_RISK_SAFE,
  ACCOUNT_RISK_SOFT,
  ACCOUNT_RISK_TITLE,
  ACCOUNT_RISK_UNKNOWN,
  ACCOUNT_COMMISSIONS_PENDING_LIVE,
  ACCOUNT_DAY_PNL_LIVE_NOTE,
  ACCOUNT_ROWS_NO_HISTORY,
  ACCOUNT_ROWS_RECONCILE,
  ACCOUNT_ROWS_RESIDUAL,
  ACCOUNT_ROW_BUYING_POWER,
  ACCOUNT_ROW_COMMISSIONS_TODAY,
  ACCOUNT_ROW_DAY_PNL,
  ACCOUNT_ROW_EXCESS_LIQUIDITY,
  ACCOUNT_ROW_FEES_TODAY,
  ACCOUNT_ROW_LONG_VALUE,
  ACCOUNT_ROW_OPEN_PNL,
  ACCOUNT_ROW_REALIZED_TODAY,
  ACCOUNT_ROW_SHORT_VALUE,
  ACCOUNT_TAG_LIVE,
  ACCOUNT_TAG_PRACTICE,
  ACCOUNT_TAG_SAMPLE,
  ACCOUNT_TAG_SIM_SCRATCH,
  ACCOUNT_TAV_HIDDEN,
  ACCOUNT_TAV_LABEL,
  ACCOUNT_TODAY_SUFFIX,
  accountRiskBotOrderSize,
  accountRiskBreakers,
  accountRiskHardLine,
  accountRiskLargestPosition,
  accountRiskSoftLine,
  type AccountRange,
} from '../constantGroups/account_page';
import { BOT_HARD_BREAKER_USD, BOT_SOFT_BREAKER_USD } from '../constantGroups/bot';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { formatSignedMoney, formatSignedPercent } from '../components/globalBarMoney';
import { dayPnlPercent, type HeaderAccountFigures } from '../components/headerAccountFigures';
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import { Money, PanelHead, toneClass, toneOf } from './accountBits';
import type { AccountDetailRows } from './accountFigures';
import type { PracticeHistory } from './accountHistoryTypes';
import { largestPosition, longMarketValue, positionSymbols, shortMarketValue, type AccountPosition } from './accountPositions';
import { EquityCurve } from './EquityCurve';
import { rangeSeries, tickDecimals } from './equityPath';

export interface RiskBreakers {
  tripped: number;
  armed: number;
}

interface Props {
  venue: DeskVenue;
  figures: HeaderAccountFigures;
  rows: AccountDetailRows;
  positions: AccountPosition[];
  history: PracticeHistory | null;
  range: AccountRange;
  onRange: (range: AccountRange) => void;
  breakers: RiskBreakers | null;
  maxSharesCap: number | null;
  hidden: boolean;
  onToggleHidden: () => void;
  nowTs: number;
  /** A stated absence that overrides the venue's own (the sample desk's V4, Sim with nothing loaded D17). */
  absence?: string | null;
  /** The sample desk: its account is Nova Marketing Sample Data, never "IBKR" (W31). */
  sample?: boolean;
}

/** `100,014.74`: cents only while the ticks are closer than a dollar (W26). */
function valueTick(value: number, step: number): string {
  const d = tickDecimals(step, 'money');
  return value.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}

export function riskLevel(dayPnl: number | null): { label: string; tone: 'up' | 'down' | 'flat' | 'muted' } {
  if (dayPnl == null) return { label: ACCOUNT_RISK_UNKNOWN, tone: 'muted' };
  if (dayPnl <= BOT_HARD_BREAKER_USD) return { label: ACCOUNT_RISK_LOCKED, tone: 'down' };
  if (dayPnl <= BOT_SOFT_BREAKER_USD) return { label: ACCOUNT_RISK_SOFT, tone: 'flat' };
  return { label: ACCOUNT_RISK_SAFE, tone: 'up' };
}

function Row({ label, children, note }: { label: string; children: React.ReactNode; note?: boolean }) {
  return (
    <div className={`acct-row${note ? ' acct-row--note' : ''}`}>
      <span className="acct-row__k">{label}</span>
      <span className="acct-row__v">{children}</span>
    </div>
  );
}

export function AccountDetailsPanel({
  venue, figures, rows, positions, history, range, onRange, breakers, maxSharesCap, hidden, onToggleHidden, nowTs,
  absence = null, sample = false,
}: Props) {
  const practice = venue !== 'live';
  const live = venue === 'live' && !sample;
  const tag = sample
    ? ACCOUNT_TAG_SAMPLE
    : venue === 'live' ? ACCOUNT_TAG_LIVE : venue === 'sim' ? ACCOUNT_TAG_SIM_SCRATCH : ACCOUNT_TAG_PRACTICE;
  const dayPct = dayPnlPercent(figures.dayPnl, figures.netLiquidation);
  const symbols = positionSymbols(positions);
  const cash = figures.cash;
  const posValue = figures.grossPositionValue ?? longMarketValue(positions);
  const donutTotal = cash != null && posValue != null ? cash + posValue : null;
  const cashShare = donutTotal && donutTotal > 0 && cash != null ? cash / donutTotal : null;
  const risk = riskLevel(figures.dayPnl);
  const largest = largestPosition(positions);
  const longValue = longMarketValue(positions);
  const shortValue = shortMarketValue(positions);
  // The range's curve, ending at the account's live value (the TAV above), W13 / W26.
  const { series, baseline } = history
    ? rangeSeries(history, 'value', { openPnl: figures.openPnl, netLiquidation: figures.netLiquidation }, nowTs)
    : { series: [], baseline: 0 };

  const r = 37;
  const c = 2 * Math.PI * r;
  const cashArc = cashShare == null ? 0 : c * cashShare;

  // Day P&L meter: the hard lock sits at the left edge, zero at the middle.
  const span = Math.abs(BOT_HARD_BREAKER_USD);
  const dayPos = figures.dayPnl == null ? null : Math.max(-span, Math.min(span, figures.dayPnl));
  const meterLeft = dayPos == null ? 50 : dayPos >= 0 ? 50 : 50 + (dayPos / span) * 50;
  const meterWidth = dayPos == null ? 0 : (Math.abs(dayPos) / span) * 50;
  const softMark = 50 + (BOT_SOFT_BREAKER_USD / span) * 50;

  return (
    <section className="acct-panel acct-panel--details" data-testid="account-details" aria-label={ACCOUNT_DETAILS_TITLE}>
      <PanelHead title={ACCOUNT_DETAILS_TITLE}>
        <span className="acct-tag" data-testid="account-details-tag">{tag}</span>
      </PanelHead>
      <div className="acct-lbl">{ACCOUNT_TAV_LABEL}</div>
      <div className="acct-hero">
        <span className="acct-hero__big acct-num" data-testid="account-tav">
          {hidden ? ACCOUNT_TAV_HIDDEN : formatMoney(figures.netLiquidation)}
        </span>
        <button
          type="button"
          className="acct-eye"
          aria-pressed={hidden}
          aria-label={hidden ? ACCOUNT_EYE_SHOW : ACCOUNT_EYE_HIDE}
          title={hidden ? ACCOUNT_EYE_SHOW : ACCOUNT_EYE_HIDE}
          data-testid="account-eye"
          onClick={onToggleHidden}
        >
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden>
            <path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" />
            {hidden ? <path d="M3 13L13 3" /> : <circle cx="8" cy="8" r="2" />}
          </svg>
        </button>
      </div>
      <div className={`acct-hero__sub acct-num ${toneClass(toneOf(figures.dayPnl))}`} data-testid="account-day-line">
        {hidden ? ACCOUNT_TAV_HIDDEN : `${formatSignedMoney(figures.dayPnl)}  ${formatSignedPercent(dayPct)}`} {ACCOUNT_TODAY_SUFFIX}
      </div>
      <div className="acct-ranges" role="tablist" aria-label="Range">
        {ACCOUNT_HISTORY_RANGES.map((r) => (
          <button
            key={r}
            type="button"
            role="tab"
            aria-selected={range === r}
            className={`acct-ranges__item${range === r ? ' is-on' : ''}`}
            data-testid={`account-range-${r}`}
            onClick={() => onRange(r)}
          >
            {r}
          </button>
        ))}
      </div>
      {history && series.length ? (
        <EquityCurve
          series={series}
          baseline={baseline}
          endTs={nowTs}
          formatTick={hidden ? () => '' : valueTick}
          lastLabel={hidden ? null : formatMoney(series[series.length - 1].value)}
          testId="account-equity-curve"
        />
      ) : (
        <div className="acct-absent acct-absent--curve" data-testid="account-equity-absent">
          {absence ?? (practice ? (history ? 'No ledger events in this range · nothing to draw' : ACCOUNT_ROWS_NO_HISTORY) : ACCOUNT_LIVE_NO_LEDGER)}
        </div>
      )}
      <div className="acct-cards">
        <div className="acct-card">
          <div className="acct-lbl">{ACCOUNT_CARD_POSITIONS}</div>
          <div className="acct-card__v acct-num" data-testid="account-positions-value">{formatMoney(posValue)}</div>
          <div className="acct-card__s">
            {symbols.length ? `${symbols.length} position${symbols.length === 1 ? '' : 's'} · ${symbols.join(', ')}` : ACCOUNT_CARD_FLAT}
          </div>
        </div>
        <div className="acct-card">
          <div className="acct-lbl">{ACCOUNT_CARD_CASH}</div>
          <div className="acct-card__v acct-num" data-testid="account-cash">{formatMoney(cash)}</div>
          <div className="acct-card__s">{ACCOUNT_CASH_SUB[venue]}</div>
        </div>
      </div>
      <div className="acct-rows" data-testid="account-rows">
        <Row label={ACCOUNT_ROW_OPEN_PNL}><Money value={rows.openPnl} signed /></Row>
        <Row label={ACCOUNT_ROW_DAY_PNL}><Money value={rows.dayPnl} signed /></Row>
        <Row label={ACCOUNT_ROW_REALIZED_TODAY}><Money value={rows.realizedToday} signed /></Row>
        <Row label={ACCOUNT_ROW_BUYING_POWER}><Money value={rows.buyingPower} /></Row>
        <Row label={ACCOUNT_ROW_EXCESS_LIQUIDITY}>
          {practice ? <span className="acct-muted" title={ACCOUNT_EXCESS_NA_PRACTICE}>n/a</span> : <Money value={rows.excessLiquidity} />}
        </Row>
        <Row label={ACCOUNT_ROW_COMMISSIONS_TODAY}>
          {rows.commissionsToday == null
            ? <span className="acct-muted" title={live ? ACCOUNT_COMMISSIONS_PENDING_LIVE : undefined}>—</span>
            : <Money value={-rows.commissionsToday} signed={rows.commissionsToday !== 0} kind="cost" />}
        </Row>
        <Row label={ACCOUNT_ROW_FEES_TODAY}>
          {rows.feesToday == null ? <span className="acct-muted">—</span> : <Money value={-rows.feesToday} signed={rows.feesToday !== 0} kind="cost" />}
        </Row>
        {rows.reconcile !== 'unknown' && (
          <p className="acct-foot acct-foot--rows" data-testid="account-rows-reconcile" data-reconcile={rows.reconcile}>
            {rows.reconcile === 'ok' ? ACCOUNT_ROWS_RECONCILE : ACCOUNT_ROWS_RESIDUAL(formatSignedMoney(rows.residual))}
          </p>
        )}
        {live && (
          <p className="acct-foot acct-foot--rows" data-testid="account-day-pnl-live-note">{ACCOUNT_DAY_PNL_LIVE_NOTE}</p>
        )}
      </div>

      <div className="acct-sub">
        <h3>{ACCOUNT_DONUT_TITLE}</h3>
        <span className="acct-dd">{ACCOUNT_DONUT_DROPDOWN}</span>
      </div>
      <div className="acct-donut" data-testid="account-donut">
        <svg viewBox="0 0 96 96" width="96" height="96" role="img" aria-label={`${ACCOUNT_DONUT_CENTER} ${cashShare == null ? '--' : `${(cashShare * 100).toFixed(1)}%`}`}>
          <circle className="acct-donut__track" cx="48" cy="48" r={r} fill="none" strokeWidth="11" />
          {cashShare != null && (
            <>
              <circle className="acct-donut__cash" cx="48" cy="48" r={r} fill="none" strokeWidth="11" strokeDasharray={`${Math.max(0, cashArc - 2)} ${c - cashArc + 2}`} transform="rotate(-90 48 48)" />
              {c - cashArc > 2 && (
                <circle className="acct-donut__pos" cx="48" cy="48" r={r} fill="none" strokeWidth="11" strokeDasharray={`${c - cashArc - 2} ${cashArc + 2}`} strokeDashoffset={-cashArc} transform="rotate(-90 48 48)" />
              )}
            </>
          )}
          <text className="acct-donut__k" x="48" y="46" textAnchor="middle">{ACCOUNT_DONUT_CENTER}</text>
          <text className="acct-donut__v" x="48" y="60" textAnchor="middle">{cashShare == null ? '--' : `${(cashShare * 100).toFixed(1)}%`}</text>
        </svg>
        <div className="acct-legend">
          <div className="acct-legend__li"><i className="acct-sw is-accent" /><span className="acct-legend__k">{ACCOUNT_LEGEND_CASH}</span><span className="acct-num">{formatMoney(cash)}{cashShare != null && <span className="acct-muted"> · {(cashShare * 100).toFixed(1)}%</span>}</span></div>
          <div className="acct-legend__li"><i className="acct-sw is-bot" /><span className="acct-legend__k">{ACCOUNT_LEGEND_POSITIONS}</span><span className="acct-num">{formatMoney(posValue)}{cashShare != null && <span className="acct-muted"> · {((1 - cashShare) * 100).toFixed(1)}%</span>}</span></div>
          <div className="acct-legend__li"><i className="acct-sw is-hollow" /><span className="acct-legend__k">{ACCOUNT_LEGEND_SHORT}</span><span className="acct-muted">{shortValue == null ? (practice ? ACCOUNT_LEGEND_SHORT_NONE : ACCOUNT_LEGEND_SHORT_NONE_LIVE) : formatMoney(shortValue)}</span></div>
          <div className="acct-legend__li"><i className="acct-sw" /><span className="acct-legend__k">{ACCOUNT_LEGEND_UNSETTLED}</span><span className="acct-muted">{practice ? ACCOUNT_LEGEND_UNSETTLED_NA : ACCOUNT_LEGEND_UNSETTLED_LIVE}</span></div>
        </div>
      </div>

      <div className="acct-sub">
        <h3>{ACCOUNT_RISK_TITLE}</h3>
        <span className={`acct-risk__level ${toneClass(risk.tone)}`} data-testid="account-risk-level">● {risk.label}</span>
      </div>
      <div className="acct-risk" data-testid="account-risk">
        <div className="acct-rrow">
          <div className="acct-rrow__kv"><span className="acct-row__k">{ACCOUNT_RISK_DAY_LOCK}</span><Money value={figures.dayPnl} signed /></div>
          <div className="acct-meter">
            <i style={{ left: `${meterLeft}%`, width: `${meterWidth}%` }} />
            <em style={{ left: '0%' }} />
            <em style={{ left: `${softMark}%` }} />
            <em className="is-zero" style={{ left: '50%' }} />
          </div>
          <div className="acct-risk__lines">
            {accountRiskSoftLine(formatSignedMoney(BOT_SOFT_BREAKER_USD, 0))}<br />
            {accountRiskHardLine(formatSignedMoney(BOT_HARD_BREAKER_USD, 0))}
          </div>
        </div>
        {/* The cap sizes each bot order; it is not a position limit, so no meter compares the two (W11). */}
        <div className="acct-rrow">
          <div className="acct-rrow__kv">
            <span className="acct-row__k">{ACCOUNT_RISK_BOT_ORDER_SIZE}</span>
            <span className={maxSharesCap == null ? 'acct-muted' : 'acct-num'} data-testid="account-bot-order-size">
              {maxSharesCap == null ? ACCOUNT_RISK_BOT_ORDER_SIZE_NONE : accountRiskBotOrderSize(formatShareQty(maxSharesCap))}
            </span>
          </div>
          <div className="acct-rrow__kv">
            <span className="acct-row__k">{ACCOUNT_RISK_LARGEST_POSITION}</span>
            <span className="acct-num" data-testid="account-largest-position">
              {accountRiskLargestPosition(formatShareQty(largest?.qty ?? 0), largest?.symbol ?? null)}
            </span>
          </div>
        </div>
        <div className="acct-rrow">
          <div className="acct-rrow__kv">
            <span className="acct-row__k">{ACCOUNT_RISK_BREAKERS}</span>
            <span className={breakers ? 'acct-num' : 'acct-muted'} data-testid="account-breakers">
              {breakers ? accountRiskBreakers(breakers.tripped, breakers.armed) : ACCOUNT_RISK_BREAKERS_NOT_EXPOSED}
            </span>
          </div>
        </div>
      </div>
      <div className="acct-rows acct-rows--mv">
        <Row label={ACCOUNT_ROW_LONG_VALUE}><Money value={longValue} /></Row>
        <Row label={ACCOUNT_ROW_SHORT_VALUE}>
          {shortValue == null ? <span className="acct-muted">{practice ? ACCOUNT_LEGEND_SHORT_NONE : ACCOUNT_LEGEND_SHORT_NONE_LIVE}</span> : <Money value={shortValue} />}
        </Row>
      </div>
    </section>
  );
}
