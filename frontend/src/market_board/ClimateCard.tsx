/**
 * The small-cap climate (ADR 053): Nova's own Gainers board by day, week or month -- runners against their
 * average, the theme of the period, a 21-session chart coloured by theme (RunnersChart: full width, hover, a large
 * view), gappers holding, halts, top runners.
 */
import { THEME_BAR_MAX, THEME_COLORS, THEME_OTHER_COLOR } from './constants';
import { count, etTime, shares, shortDate, signedPct } from './format';
import { PeriodSwitch, Sym } from './parts';
import { RunnersChart } from './RunnersChart';
import type { Climate, Period } from './types';

const WORD: Record<Period, string> = { '1D': 'day', '7D': 'week', '30D': 'month' };
const PILL: Record<NonNullable<Climate['temperature']>, string> = { hot: 'HOT', normal: 'NORMAL', cold: 'COLD' };

/** One colour per theme, stable across the chart, the bar and the chips (most runners first). */
function palette(c: Climate): Map<string, string> {
  const map = new Map<string, string>();
  c.themes.filter((t) => t.name !== 'Unclassified').slice(0, THEME_COLORS.length)
    .forEach((t, i) => map.set(t.name, THEME_COLORS[i]));
  return map;
}

function color(colors: Map<string, string>, name: string): string {
  return colors.get(name) ?? THEME_OTHER_COLOR;
}

function ThemeBar({ c, colors }: { c: Climate; colors: Map<string, string> }) {
  const total = c.themes.reduce((a, t) => a + t.count, 0);
  if (!total) return <div className="mk-themes mk-themes--empty">no runners yet</div>;
  const named = c.themes.filter((t) => t.count > 0).slice(0, THEME_BAR_MAX);
  const rest = total - named.reduce((a, t) => a + t.count, 0);
  const segs = [...named.map((t) => ({ name: t.name, v: t.count })), ...(rest > 0 ? [{ name: 'Other', v: rest }] : [])];
  return (
    <div className="mk-themes">
      {segs.map((s) => {
        const share = s.v / total;
        return (
          <i key={s.name} style={{ width: `${share * 100}%`, background: s.name === 'Other' ? THEME_OTHER_COLOR : color(colors, s.name) }}
            title={`${s.name}: ${s.v}`}>
            {share > 0.11 ? `${s.name} ${s.v}` : share > 0.03 ? s.v : ''}
          </i>
        );
      })}
    </div>
  );
}

export function ClimateCard({ c, onPeriod, onOpen }: { c: Climate | null; onPeriod: (p: Period) => void; onOpen?: (s: string) => void }) {
  if (!c) {
    return (
      <section className="mk-card mk-climate" data-testid="market-climate">
        <header className="mk-card__head"><h3>Small-cap climate</h3></header>
        <p className="mk-wait" role="status">Reading Nova&apos;s scanner history …</p>
      </section>
    );
  }
  const colors = palette(c);
  const word = WORD[c.period];
  const many = c.period !== '1D';
  const base = c.baseline;
  const avgLine = (v: number | null | undefined) => {
    if (!base || v == null) return 'no average yet';
    return many ? `avg ${v}/day` : `avg ${v} by now`;
  };
  const cover = c.period === '1D' ? 'today so far' : `${shortDate(c.from)} – ${shortDate(c.to)} · ${c.sessions} sessions · ${c.covered} of ${c.sessions} recorded`;
  const gl = c.gappers;
  return (
    <section className="mk-card mk-climate" data-testid="market-climate">
      <header className="mk-card__head">
        <h3>Small-cap climate</h3>
        <PeriodSwitch value={c.period} onChange={onPeriod} label="Small-cap climate period" />
        {c.temperature ? <span className={`mk-pill is-${c.temperature} mk-push`}>{PILL[c.temperature]} {word.toUpperCase()}</span> : null}
      </header>
      <p className="mk-cover">{cover} · Nova&apos;s Gainers board (top {c.lens.rank_max}, ${c.lens.price_min}+)</p>
      <div className="mk-climate__top">
        {(['up20', 'up50', 'up100'] as const).map((k) => (
          <div key={k} className="mk-box" title={base ? `Average over Nova's ${base.days} recorded sessions before this ${word}${many ? '' : ', at this time of day'}` : 'Nova has not recorded enough sessions to average'}>
            <div className="mk-t">Up {k.slice(2)}%+</div>
            <div className="mk-v mk-v--big is-up">{count(c.counts[k])}</div>
            <div className="mk-s">{k === 'up20' && many && c.per_day != null ? `${c.per_day}/day · ` : ''}{avgLine(base?.[k] ?? null)}</div>
          </div>
        ))}
      </div>
      <RunnersChart c={c} color={(name) => color(colors, name)} period={word} />
      <div className="mk-climate__theme">
        <span className="mk-t">Theme of the {word}</span>
        {c.theme ? (
          <>
            <span className="mk-climate__tname" style={{ color: color(colors, c.theme.name) }}>{c.theme.name}</span>
            <span className="mk-small">
              {c.theme.count} of {c.theme.total} runners ({c.theme.share_pct ?? '--'}%)
              {c.theme.prev_share_pct != null ? <> · <span className={(c.theme.share_pct ?? 0) >= c.theme.prev_share_pct ? 'is-up' : 'is-down'}>
                {(c.theme.share_pct ?? 0) >= c.theme.prev_share_pct ? '▲' : '▼'} from {c.theme.prev_share_pct}% last {word}</span></> : null}
              {' · '}<span className="mk-muted">industry from IBKR</span>
            </span>
          </>
        ) : <span className="mk-small mk-muted">no classified runners yet</span>}
      </div>
      <ThemeBar c={c} colors={colors} />
      {many ? (
        <div className="mk-legend">
          {c.themes.filter((t) => t.count || t.prev_count).slice(0, 7).map((t) => {
            const d = t.count - t.prev_count;
            return (
              <span key={t.name}><b style={{ color: color(colors, t.name) }}>&#9632;</b> {t.name} <b>{t.count}</b>{' '}
                <span className={d > 0 ? 'is-up' : d < 0 ? 'is-down' : 'mk-muted'}>{d > 0 ? '+' : d < 0 ? '−' : '±'}{Math.abs(d)}</span></span>
            );
          })}
          <span className="mk-muted">± = vs last {word}</span>
        </div>
      ) : null}
      <div className="mk-climate__mid">
        <div className="mk-box" title={gl.gone ? `${gl.gone} gapper(s) left the board, so whether they held is unknown` : undefined}>
          <div className="mk-t">Gappers holding</div>
          <div className="mk-row"><span className="mk-v is-warn">{gl.total ? `${gl.held} of ${gl.total}` : '--'}</span>
            <span className="mk-s">{gl.total ? `${gl.rate_pct}% held their open` : 'no 20%+ gappers after 09:30 yet'}{gl.baseline_rate_pct != null ? ` · usual ${gl.baseline_rate_pct}%` : ''}</span></div>
        </div>
        <div className="mk-box" title={c.halts.by_side_why}>
          <div className="mk-t">Halts</div>
          <div className="mk-row"><span className="mk-v">{count(c.halts.count)}</span>
            <span className="mk-s">{c.halts.last ? `last ${c.halts.last.symbol} ${etTime(c.halts.last.at)}` : 'none'} · up / down not recorded</span></div>
        </div>
      </div>
      <div className="mk-toprun">
        <span className="mk-t">{c.top.length > 1 ? 'Top runners' : 'Top runner'}</span>
        {c.top.length === 0 ? <span className="mk-muted">none yet</span> : null}
        {c.top.length === 1 ? (
          <>
            <Sym symbol={c.top[0].symbol} onOpen={onOpen} />
            <span className="is-up mk-b">{signedPct(c.top[0].change_pct, 0)}</span>
            {c.top[0].price != null ? <span>${c.top[0].price.toFixed(2)}</span> : null}
            <span className="mk-muted">float {shares(c.top[0].float_shares)} · {c.top[0].theme}{c.top[0].news_at ? ` · news ${etTime(c.top[0].news_at)}` : ''}</span>
          </>
        ) : c.top.map((r) => (
          <span key={`${r.symbol}-${r.date}`} className="mk-tchip">
            <b style={{ color: color(colors, r.theme) }}>&#9679;</b> <Sym symbol={r.symbol} onOpen={onOpen} />{' '}
            <span className="is-up mk-b">{signedPct(r.change_pct, 0)}</span> <span className="mk-muted">{shortDate(r.date)}</span>
          </span>
        ))}
      </div>
    </section>
  );
}
