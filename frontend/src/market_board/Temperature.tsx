/**
 * The small-cap temperature inside the climate card (ADR 053 amendment 2026-10-25): the numbers each label is made
 * of. A day shows its 100%+ runners and the money in the top 5 gainers against the usual; a week or a month shows
 * each session's label as a strip, how often runners held, and the month's score. The rule is one click away.
 */
import { useState } from 'react';
import { TEMP_RULE } from './constants';
import { count, money, shortDate, signedPct } from './format';
import type { Heat, HeatDay, Period } from './types';

function dayTitle(d: HeatDay): string {
  if (!d.board) return `${shortDate(d.date)}: Nova recorded no Gainers board`;
  if (d.runners_100 == null) return `${shortDate(d.date)}: no recording near this time`;
  const usual = d.usual_money != null ? ` vs usual ${money(d.usual_money)}` : ` (no usual yet: ${d.usual_days} sessions before)`;
  return `${shortDate(d.date)}: ${d.label ?? 'no label'} · ${d.runners_100} up 100%+ · top 5 ${money(d.money)}${usual}`;
}

export function Temperature({ heat, period }: { heat: Heat; period: Period }) {
  const [rule, setRule] = useState(false);
  const today = heat.days[heat.days.length - 1];
  return (
    <div className="mk-heat" data-testid="market-heat">
      <div className="mk-heat__head">
        <span className="mk-t">Temperature</span>
        {heat.label ? null : <span className="mk-small mk-muted">{heat.why ?? 'no label yet'}</span>}
        <button type="button" className="mk-link mk-push" aria-expanded={rule} onClick={() => setRule((v) => !v)}>
          the rule &#9432;
        </button>
      </div>
      {rule ? <p className="mk-heat__rule" role="note">{TEMP_RULE[period]}</p> : null}
      {period === '1D' ? (
        <div className="mk-heat__nums">
          <div className="mk-box">
            <div className="mk-t">Up 100%+ (${heat.price_min}–{heat.price_max})</div>
            <div className="mk-v">{count(today?.runners_100)}</div>
            <div className="mk-s">hot needs 2 or more</div>
          </div>
          <div className="mk-box" title="Shares traded x last price of the five biggest gainers">
            <div className="mk-t">Money in the top 5</div>
            <div className="mk-v">{money(today?.money)}</div>
            <div className="mk-s">
              {!today?.board
                ? 'no Gainers board this session'
                : today.usual_money != null
                  ? `usual ${money(today.usual_money)} · median of ${today.usual_days} sessions`
                  : `no usual yet · ${today.usual_days} sessions recorded before`}
            </div>
          </div>
        </div>
      ) : (
        <>
          <div className="mk-heat__days" role="list" aria-label="Each session's temperature, oldest first">
            {heat.days.map((d) => (
              <i key={d.date} role="listitem" className={`is-${d.label ?? 'none'}`} title={dayTitle(d)} />
            ))}
          </div>
          <div className="mk-s mk-heat__sum">
            {heat.hot} hot · {heat.warm} warm · {heat.cold} cold
            {heat.hold_pct != null ? ` · runners held ${Math.round(heat.hold_pct)}% of the time` : ''}
            {heat.score_pct != null ? ` · score ${signedPct(heat.score_pct, 0)}` : ''}
          </div>
          <div className="mk-heat__key" aria-hidden="true">
            <span><i className="is-hot" />hot</span><span><i className="is-warm" />warm</span>
            <span><i className="is-cold" />cold</span><span><i className="is-none" />no label (no board, or too little history)</span>
          </div>
        </>
      )}
    </div>
  );
}
