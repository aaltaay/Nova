/**
 * Settings > Trade > Stocks — Default Order Values form.
 */
import {
  TRADE_DEFAULTS_EH_HINT,
  TRADE_DEFAULTS_HOURS_LABEL,
  TRADE_DEFAULTS_LIMIT_SOURCE_LABEL,
  TRADE_DEFAULTS_ORDER_TYPE_LABEL,
  TRADE_DEFAULTS_QUANTITY_LABEL,
  TRADE_DEFAULTS_SECTION_TITLE,
  TRADE_DEFAULTS_STOP_OFFSET_LABEL,
  TRADE_DEFAULTS_TIF_HINT,
  TRADE_DEFAULTS_TIF_LABEL,
  type TradeDefaultLimitSource,
  type TradeDefaultOrderType,
} from '../constantGroups/trade_defaults';
import {
  writeTradeDefaultsPrefs,
  type TradeDefaultsPrefs,
} from './tradeDefaultsPrefs';

interface Props {
  prefs: TradeDefaultsPrefs;
  onChange: (next: TradeDefaultsPrefs) => void;
}

export function TradeStocksDefaultsForm({ prefs, onChange }: Props) {
  function patch(partial: Partial<TradeDefaultsPrefs>) {
    const next = { ...prefs, ...partial, v: 1 as const, tif: 'DAY' as const };
    writeTradeDefaultsPrefs(next);
    onChange(next);
  }

  return (
    <div className="trade-defaults-form" data-testid="trade-stocks-defaults">
      <h3 className="settings-block-title">{TRADE_DEFAULTS_SECTION_TITLE}</h3>

      <div className="trade-defaults-row">
        <label htmlFor="trade-def-order-type">{TRADE_DEFAULTS_ORDER_TYPE_LABEL}</label>
        <select
          id="trade-def-order-type"
          value={prefs.orderType}
          onChange={(e) =>
            patch({ orderType: e.target.value as TradeDefaultOrderType })
          }
        >
          <option value="MKT">Market</option>
          <option value="LMT">Limit</option>
          <option value="STP">Stop</option>
        </select>
      </div>

      <div className="trade-defaults-row">
        <label htmlFor="trade-def-qty">{TRADE_DEFAULTS_QUANTITY_LABEL}</label>
        <input
          id="trade-def-qty"
          type="number"
          min={1}
          step={1}
          value={prefs.quantity}
          onChange={(e) => {
            const n = Number(e.target.value);
            if (Number.isFinite(n) && n > 0) patch({ quantity: Math.floor(n) });
          }}
        />
      </div>

      <label className="trade-prefs-check" htmlFor="trade-def-hours">
        <input
          id="trade-def-hours"
          type="checkbox"
          checked={prefs.tradingHours === 'extended'}
          onChange={(e) =>
            patch({
              tradingHours: e.target.checked ? 'extended' : 'rth',
            })
          }
        />
        <span>
          <strong>{TRADE_DEFAULTS_HOURS_LABEL}</strong>
          <span className="settings-block-hint">{TRADE_DEFAULTS_EH_HINT}</span>
        </span>
      </label>

      <div className="trade-defaults-row">
        <label htmlFor="trade-def-tif">{TRADE_DEFAULTS_TIF_LABEL}</label>
        <select id="trade-def-tif" value="DAY" disabled title={TRADE_DEFAULTS_TIF_HINT}>
          <option value="DAY">DAY</option>
          <option value="GTC" disabled>
            GTC (soon)
          </option>
        </select>
      </div>
      <p className="settings-block-hint">{TRADE_DEFAULTS_TIF_HINT}</p>

      <div className="trade-defaults-row">
        <label htmlFor="trade-def-limit-src">
          {TRADE_DEFAULTS_LIMIT_SOURCE_LABEL}
        </label>
        <select
          id="trade-def-limit-src"
          value={prefs.limitPriceSource}
          onChange={(e) =>
            patch({
              limitPriceSource: e.target.value as TradeDefaultLimitSource,
            })
          }
        >
          <option value="ask_bid">Ask / Bid</option>
          <option value="last">Last</option>
          <option value="mid">Mid</option>
        </select>
      </div>

      <div className="trade-defaults-row">
        <label htmlFor="trade-def-stop-pct">{TRADE_DEFAULTS_STOP_OFFSET_LABEL}</label>
        <input
          id="trade-def-stop-pct"
          type="number"
          min={0}
          step={0.1}
          value={prefs.stopOffsetPct}
          onChange={(e) => {
            const n = Number(e.target.value);
            if (Number.isFinite(n) && n >= 0) patch({ stopOffsetPct: n });
          }}
        />
      </div>
    </div>
  );
}
