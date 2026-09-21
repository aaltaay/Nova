/**
 * Settings > Trade > Stocks — Default Order Values form.
 */
import {
  TRADE_DEFAULT_LEG_PCT_MAX,
  TRADE_DEFAULT_LEG_PCT_MIN,
  TRADE_DEFAULT_TIFS,
  TRADE_DEFAULTS_EH_HINT,
  TRADE_DEFAULTS_HOURS_LABEL,
  TRADE_DEFAULTS_LEGS_HINT,
  TRADE_DEFAULTS_LEGS_LABEL,
  TRADE_DEFAULTS_LEGS_OFFSET_HINT,
  TRADE_DEFAULTS_LIMIT_SOURCE_LABEL,
  TRADE_DEFAULTS_ORDER_TYPE_LABEL,
  TRADE_DEFAULTS_QUANTITY_LABEL,
  TRADE_DEFAULTS_SECTION_TITLE,
  TRADE_DEFAULTS_STOP_LOSS_LABEL,
  TRADE_DEFAULTS_STOP_OFFSET_LABEL,
  TRADE_DEFAULTS_TAKE_PROFIT_LABEL,
  TRADE_DEFAULTS_TIF_HINT,
  TRADE_DEFAULTS_TIF_LABEL,
  type TradeDefaultLimitSource,
  type TradeDefaultOrderType,
  type TradeDefaultTif,
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
    const next = { ...prefs, ...partial, v: 1 as const };
    writeTradeDefaultsPrefs(next);
    onChange(next);
  }

  function patchLegPct(key: 'takeProfitPct' | 'stopLossPct', raw: string) {
    const value = Number(raw);
    if (
      Number.isFinite(value) &&
      value >= TRADE_DEFAULT_LEG_PCT_MIN &&
      value <= TRADE_DEFAULT_LEG_PCT_MAX
    ) {
      patch({ [key]: value } as Partial<TradeDefaultsPrefs>);
    }
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
        <select
          id="trade-def-tif"
          value={prefs.tif}
          title={TRADE_DEFAULTS_TIF_HINT}
          onChange={(e) => patch({ tif: e.target.value as TradeDefaultTif })}
        >
          {TRADE_DEFAULT_TIFS.map((tif) => (
            <option key={tif} value={tif}>
              {tif}
            </option>
          ))}
        </select>
      </div>
      <p className="settings-block-hint">{TRADE_DEFAULTS_TIF_HINT}</p>

      <label className="trade-prefs-check" htmlFor="trade-def-legs">
        <input
          id="trade-def-legs"
          type="checkbox"
          checked={prefs.protectiveLegs}
          onChange={(e) => patch({ protectiveLegs: e.target.checked })}
        />
        <span>
          <strong>{TRADE_DEFAULTS_LEGS_LABEL}</strong>
          <span className="settings-block-hint">{TRADE_DEFAULTS_LEGS_HINT}</span>
        </span>
      </label>

      {prefs.protectiveLegs && (
        <>
          <div className="trade-defaults-row">
            <label htmlFor="trade-def-tp-pct">
              {TRADE_DEFAULTS_TAKE_PROFIT_LABEL}
            </label>
            <input
              id="trade-def-tp-pct"
              type="number"
              min={TRADE_DEFAULT_LEG_PCT_MIN}
              max={TRADE_DEFAULT_LEG_PCT_MAX}
              step={0.1}
              value={prefs.takeProfitPct}
              onChange={(e) => patchLegPct('takeProfitPct', e.target.value)}
            />
          </div>
          <div className="trade-defaults-row">
            <label htmlFor="trade-def-sl-pct">{TRADE_DEFAULTS_STOP_LOSS_LABEL}</label>
            <input
              id="trade-def-sl-pct"
              type="number"
              min={TRADE_DEFAULT_LEG_PCT_MIN}
              max={TRADE_DEFAULT_LEG_PCT_MAX}
              step={0.1}
              value={prefs.stopLossPct}
              onChange={(e) => patchLegPct('stopLossPct', e.target.value)}
            />
          </div>
          <p className="settings-block-hint">{TRADE_DEFAULTS_LEGS_OFFSET_HINT}</p>
        </>
      )}

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
