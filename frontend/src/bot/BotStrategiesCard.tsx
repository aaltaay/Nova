/**
 * The operator's playbook on the Bots page (ADR 027): the setup that plays --
 * first pullback, with its rules, the tape gate and the read-out that unlocks
 * Strategy -- and the rest of the material's setups with what the research
 * said, each waiting on a scanner of its own. Nothing here places an order.
 */
import {
  BOT_ADD_SETUP_HINT,
  BOT_ADD_SETUP_TITLE,
  BOT_CHOSEN_BADGE,
  BOT_FIRST_PULLBACK_RULES,
  BOT_LEVEL_LABELS,
  BOT_NO_SCANNER_TITLE,
  BOT_READOUT_RULE,
  BOT_READOUT_STATE_LABELS,
  BOT_READOUT_TITLE,
  BOT_SETUP_BLURBS,
  BOT_SETUP_FIRST_PULLBACK,
  BOT_SETUP_IDS,
  BOT_SETUP_LABELS,
  BOT_SETUP_NEXT,
  BOT_SETUP_RESEARCH,
  BOT_STRATEGIES_SUB,
  BOT_STRATEGIES_TITLE,
  BOT_TAPE_GATE_LINES,
  TAPE_VERDICT_TITLES,
} from '../constants';
import { fmtR, readoutProgress } from './botsPageFormat';
import type { BotReadout, BotSession } from './types';

function LevelTag({ level, playing }: { level: number; playing: boolean }) {
  const shown = playing ? (level > 2 ? 2 : level) : 0;
  return (
    <span className="bots-levels" title={playing ? 'The bot level, set in the card above' : BOT_NO_SCANNER_TITLE}>
      {([0, 1, 2] as const).map(n => (
        <span key={n} className={`bots-levels__opt${shown === n ? ' is-on' : ''}${!playing && n > 0 ? ' is-off' : ''}`}>
          {BOT_LEVEL_LABELS[n]}
        </span>
      ))}
    </span>
  );
}

function Readout({ readout }: { readout: BotReadout | undefined }) {
  if (!readout) {
    return <div className="bots-readout" data-testid="bots-readout">Read-out not reported by this API.</div>;
  }
  const min = readout.rules?.min_go ?? 50;
  const minR = readout.rules?.min_net_r ?? 0.2;
  return (
    <div className={`bots-readout bots-readout--${readout.state}`} data-testid="bots-readout" title={readout.reason}>
      <div className="bots-readout__head">
        <span>{BOT_READOUT_TITLE}</span>
        <span className="bots-readout__state">{BOT_READOUT_STATE_LABELS[readout.state] ?? readout.state}</span>
        <b data-testid="bots-readout-count">{readout.go.triggered} / {min}</b>
        <span className="bots-readout__muted">go setups triggered</span>
      </div>
      <div className="bots-readout__bar"><i style={{ width: `${readoutProgress(readout)}%` }} /></div>
      <div className="bots-readout__nums">
        <span>GO so far <b>{fmtR(readout.go.avg_net_r)}</b></span>
        <span>vs blind / wait <b>{fmtR(readout.control.avg_net_r)}</b></span>
        <span className="bots-readout__muted">needs &gt; +{minR.toFixed(1)}R and above blind / wait</span>
      </div>
      <p className="bots-readout__rule">{BOT_READOUT_RULE} {readout.reason}</p>
    </div>
  );
}

export function BotStrategiesCard({ session }: { session: BotSession }) {
  const chosen = session.setup || BOT_SETUP_FIRST_PULLBACK;
  const scanner = new Map((session.setups ?? []).map(s => [s.id, s.scanner]));
  const others = BOT_SETUP_IDS.filter(id => id !== chosen);
  return (
    <section className="bots-card bots-strats" data-testid="bots-strategies">
      <header className="bots-card__head">
        <h3>{BOT_STRATEGIES_TITLE}</h3>
        <span className="bots-card__sub">{BOT_STRATEGIES_SUB}</span>
      </header>

      <article className="bots-strat bots-strat--chosen" data-testid={`bots-setup-${chosen}`}>
        <div className="bots-strat__head">
          <b>{BOT_SETUP_LABELS[chosen] ?? chosen}</b>
          <span className="bots-badge">★ {BOT_CHOSEN_BADGE}</span>
          <LevelTag level={session.level} playing />
        </div>
        {chosen === BOT_SETUP_FIRST_PULLBACK ? (
          <>
            <dl className="bots-rules">
              {BOT_FIRST_PULLBACK_RULES.map(([k, v]) => (
                <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
              ))}
            </dl>
            <div className="bots-tape" aria-label="Tape gate">
              {BOT_TAPE_GATE_LINES.map(([verdict, text]) => (
                <span key={verdict} className={`bots-tape__v bots-tape__v--${verdict}`} title={TAPE_VERDICT_TITLES[verdict]}>
                  <b>{verdict.toUpperCase()}</b> {text}
                </span>
              ))}
            </div>
            <Readout readout={session.readout} />
            <p className="bots-strat__research">{BOT_SETUP_RESEARCH[chosen]?.text}</p>
          </>
        ) : (
          <p className="bots-strat__blurb">{BOT_SETUP_BLURBS[chosen]}</p>
        )}
      </article>

      <div className="bots-strat-grid">
        {others.map(id => (
          <article key={id} className="bots-strat" data-testid={`bots-setup-${id}`}
            title={scanner.get(id) ? undefined : BOT_NO_SCANNER_TITLE}>
            <div className="bots-strat__head">
              <b>{BOT_SETUP_LABELS[id] ?? id}</b>
              <LevelTag level={0} playing={false} />
            </div>
            <p className="bots-strat__blurb">{BOT_SETUP_BLURBS[id]}</p>
            <p className={`bots-strat__research bots-strat__research--${BOT_SETUP_RESEARCH[id]?.verdict ?? 'not_tested'}`}>
              {BOT_SETUP_RESEARCH[id]?.text}
            </p>
            <p className="bots-strat__next">{scanner.get(id) ? 'Scanner live' : BOT_SETUP_NEXT[id] ?? 'No scanner yet'}</p>
          </article>
        ))}
        <article className="bots-strat bots-strat--add" data-testid="bots-add-setup">
          <b>+ {BOT_ADD_SETUP_TITLE}</b>
          <p className="bots-strat__blurb">{BOT_ADD_SETUP_HINT}</p>
        </article>
      </div>
    </section>
  );
}
