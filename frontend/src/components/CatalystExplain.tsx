/**
 * Everything behind one Catalyst cell (ADR 028 amendment 2026-10-12): the call, the price it was read at and
 * why that price, the news with its source and time, the ladder -- each cause in the rules' order, whether it
 * fits and why -- and every fact with its source and age. It shows only what the read holds; an unknown says
 * unknown. The Catalyst hover card and the Trader focus rail's card both show it.
 */
import {
  CATALYST_ALSO_TRUE,
  CATALYST_BOARD_WORDS,
  CATALYST_CATEGORY_LABELS,
  CATALYST_CHECKS_TITLE,
  CATALYST_LADDER_NOTE,
  CATALYST_LADDER_TITLE,
  CATALYST_NEWS_TITLE,
  CATALYST_PRICED_BY_WORDS,
  CATALYST_SOURCE_LABELS,
  CATALYST_STEP_MARKS,
  CATALYST_STEP_TITLES,
  WHY_MOVING_POSSIBLE_TITLE,
  WHY_MOVING_READING,
  WHY_MOVING_REPLAY_PREFIX,
  WHY_MOVING_REPLAY_SUFFIX,
  WHY_MOVING_RULES_NOTE,
} from '../constants';
import type { CatalystVerdict } from '../types/catalystVerdict';
import type { WhyMovingRead, WhyStep } from '../types/whyMoving';
import { catalystFace } from '../utils/catalystCause';
import { agoLabel } from '../utils/catalystVerdict';
import { fmtPct, fmtPrice } from '../utils/quoteFormat';
import { CatalystMark } from './CatalystMark';
import { CheckRow } from './WhyMovingSection';
import './catalystCell.css';
import './whyMoving.css';
import { TickerLink } from './TickerLink';

const ET = 'America/New_York';

/** "Oct 12 06:12 ET". */
export function etMoment(sec: number): string {
  const d = new Date(sec * 1000);
  const day = d.toLocaleDateString('en-US', { timeZone: ET, month: 'short', day: 'numeric' });
  const time = d.toLocaleTimeString('en-US', { timeZone: ET, hour12: false, hour: '2-digit', minute: '2-digit' });
  return `${day} ${time} ET`;
}

function stepState(fits: boolean | null): 'yes' | 'no' | 'unknown' {
  return fits === true ? 'yes' : fits === false ? 'no' : 'unknown';
}

/** The rungs up to the call, then the later causes that fit too. */
export function ladderParts(steps: WhyStep[]): { shown: WhyStep[]; also: WhyStep[] } {
  if (steps.length === 0) return { shown: [], also: [] };
  if (steps[0].fits !== true) return { shown: steps.slice(0, 1), also: [] };
  const at = steps.findIndex((s, i) => i > 0 && s.fits === true);
  if (at < 0) return { shown: steps, also: [] };
  return { shown: steps.slice(0, at + 1), also: steps.slice(at + 1).filter(s => s.fits === true && s.kind !== 'unexplained') };
}

function Step({ s, chosen }: { s: WhyStep; chosen: boolean }) {
  const state = stepState(s.fits);
  return (
    <li className={`cx-step cx-step--${state}${chosen ? ' cx-step--chosen' : ''}`} data-step={s.kind} data-fits={state}>
      <span className="cx-step-mark" aria-label={CATALYST_STEP_TITLES[state]}>{CATALYST_STEP_MARKS[state]}</span>
      <span className="cx-step-name">{s.name}</span>
      {/* "--" as two non-breaking hyphens, so a wrapped reason never splits it across lines. */}
      <span className="cx-step-why">{s.why.replace(/--/g, '‑‑')}</span>
    </li>
  );
}

function headline(v: CatalystVerdict): string | null {
  const title = v.title?.trim();
  if (!title) return null;
  return v.source === 'edgar' && title.includes(' | ') ? title.split(' | ').slice(1).join(' | ').trim() : title;
}

function NewsLine({ v, nowMs }: { v: CatalystVerdict; nowMs: number }) {
  const title = headline(v);
  if (!title || (v.verdict !== 'catalyst' && v.verdict !== 'negative' && v.verdict !== 'routine_only')) return null;
  const what = [
    v.category ? CATALYST_CATEGORY_LABELS[v.category] ?? v.category : null,
    v.strength,
    v.source ? CATALYST_SOURCE_LABELS[v.source] ?? v.source : null,
    v.published_ts != null ? `${etMoment(v.published_ts)} (${agoLabel(v.published_ts, nowMs)})` : null,
  ].filter(Boolean).join(' · ');
  return (
    <div className="cx-news" data-testid="catalyst-news">
      <div className="cx-section-title">{CATALYST_NEWS_TITLE}</div>
      <div className="cx-news-meta">{what}</div>
      <div className="cx-news-title">{title}</div>
    </div>
  );
}

function ReadAt({ symbol, read }: { symbol: string; read: WhyMovingRead }) {
  const f = read.facts;
  if (!f || f.price == null) return null;
  const how = f.priced_by ? CATALYST_PRICED_BY_WORDS[f.priced_by] : null;
  const board = f.board ? CATALYST_BOARD_WORDS[f.board] ?? f.board : null;
  const trade = f.priced_by === 'board_row' && f.last_trade ? f.last_trade : null;
  return (
    <div className="cx-readat" data-testid="catalyst-read-at" data-priced-by={f.priced_by ?? ''}>
      <span>
        <TickerLink symbol={symbol} /> read at <b>{fmtPrice(f.price)} ({fmtPct(f.change_pct, '?')})</b>
        {how ? ` -- ${how}` : ''}{board ? ` (${board})` : ''}
      </span>
      {trade && (
        <span className="cx-readat-trade">
          Last trade {fmtPrice(trade.price)} ({fmtPct(trade.change_pct, '?')}) at {etMoment(trade.ts)}
        </span>
      )}
    </div>
  );
}

interface Props {
  symbol: string;
  read: WhyMovingRead | null;
  loading?: boolean;
  error?: string | null;
  /** The row's own verdict, for the mark while the read has none. */
  rowVerdict?: CatalystVerdict | null;
}

export function CatalystExplain({ symbol, read, loading = false, error = null, rowVerdict = null }: Props) {
  // A replay's facts are as of the playhead, so ages count back from it.
  const nowMs = read?.replay ? read.generated_at * 1000 : Date.now();
  if (!read) {
    return (
      <div className="cx" data-testid="catalyst-explain">
        <div className="cx-head"><span className="cx-cause">{loading ? WHY_MOVING_READING : error ?? WHY_MOVING_READING}</span></div>
      </div>
    );
  }
  const { likely } = read;
  const face = catalystFace(read, rowVerdict, nowMs);
  const { shown, also } = ladderParts(likely.steps ?? []);
  const chosen = shown.length ? shown[shown.length - 1].kind : null;
  const verdict = read.facts?.catalyst ?? rowVerdict;
  return (
    <div className="cx" data-testid="catalyst-explain" data-why-kind={likely.kind}>
      <div className="cx-head">
        <CatalystMark face={face} />
        <span className="cx-cause">{likely.label}</span>
        {likely.confidence === 'possible' && <span className="wm-possible" title={WHY_MOVING_POSSIBLE_TITLE}>possible</span>}
      </div>
      {/* The news's detail is its headline, which the news block below shows with its source and time. */}
      {likely.detail && !(verdict && likely.detail === headline(verdict)) && <p className="cx-detail">{likely.detail}</p>}
      <ReadAt symbol={symbol} read={read} />
      {read.replay && (
        <div className="cx-readat">{`${WHY_MOVING_REPLAY_PREFIX} ${etMoment(read.generated_at)} ${WHY_MOVING_REPLAY_SUFFIX}`}</div>
      )}
      {verdict && <NewsLine v={verdict} nowMs={nowMs} />}
      {shown.length > 0 && (
        <div className="cx-ladder" data-testid="catalyst-ladder">
          <div className="cx-section-title">{CATALYST_LADDER_TITLE}</div>
          <div className="cx-note">{CATALYST_LADDER_NOTE}</div>
          <ol className="cx-steps">
            {shown.map(s => <Step key={s.kind} s={s} chosen={s.kind === chosen && s.kind !== 'move'} />)}
          </ol>
          {also.length > 0 && (
            <div className="cx-also">
              <span className="cx-section-title">{CATALYST_ALSO_TRUE}</span>
              <ol className="cx-steps">{also.map(s => <Step key={s.kind} s={s} chosen={false} />)}</ol>
            </div>
          )}
        </div>
      )}
      {read.checks.length > 0 && (
        <div className="cx-checks">
          <div className="cx-section-title">{CATALYST_CHECKS_TITLE}</div>
          <ul className="wm-checks">
            {read.checks.map(c => <CheckRow key={c.id} c={c} nowMs={nowMs} showSource />)}
          </ul>
        </div>
      )}
      {error && <div className="cn-error" role="status">{error}</div>}
      {read.checks.length > 0 && <div className="wm-note">{WHY_MOVING_RULES_NOTE} Rules {read.rules_version}.</div>}
    </div>
  );
}
