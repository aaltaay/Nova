/**
 * The strategies in three buckets side by side (ADR 049, #778 step 5): **On · the bot trades these**, **Eyes ·
 * alerts you, Nova never trades** and **Off · watches and scores, silent**. One bot for both sides: each row
 * carries its ▲ LONG or ▼ SHORT tag, how far its evidence has come (a short's five-year test, a long's read-out)
 * and its Off · Eyes · On -- the same switch as its card, locked at On while a short's test has not passed.
 * Under them, the one rule for a stock: one trade at a time, never a flip, both sides counted. The cards follow.
 */
import {
  BOTS_BUCKET_BOT_OFF,
  BOTS_BUCKET_EMPTY,
  BOTS_BUCKETS,
  BOTS_BUCKETS_RULE,
} from '../constantGroups/bots_page';
import { SETUP_SIDE_TAG, SETUP_SIDE_TAG_TIPS } from '../constantGroups/short_setups';
import { tipProps } from '../ux/hoverTip';
import { BotLevelSwitch } from './BotLevelSwitch';
import { bucketsOf, statusOf, type BucketRow } from './strategyBuckets';
import './botStrategyBuckets.css';

interface Props {
  rows: readonly BucketRow[];
  /** The Bot switch is on for this venue: off, the On bucket alerts like Eyes, and says so. */
  botOn: boolean;
  /** Why every switch is locked now (saving); null when they are not. */
  why: string | null;
  onLevel: (id: string, level: number) => void;
}

function Line({ row, why, onLevel }: { row: BucketRow; why: string | null; onLevel: Props['onLevel'] }) {
  const status = statusOf(row);
  return (
    <div className="bots-bucket__row" data-testid={`bots-bucket-row-${row.id}`}>
      <span className="bots-bucket__name">{row.label}</span>
      <span className={`bots-sidetag bots-sidetag--${row.side}`}
        {...tipProps(SETUP_SIDE_TAG_TIPS[row.side], SETUP_SIDE_TAG[row.side])}>{SETUP_SIDE_TAG[row.side]}</span>
      <span className={`bots-bucket__status bots-bucket__status--${status.tone}`} data-testid={`bots-bucket-status-${row.id}`}
        {...tipProps(status.tip, status.text)}>{status.text}</span>
      <BotLevelSwitch id={row.id} label={row.label} own={row.own} why={why}
        onLock={row.side === 'short' ? row.locked : null} onLevel={onLevel} testPrefix="bots-bucket-level" />
    </div>
  );
}

export function BotStrategyBuckets({ rows, botOn, why, onLevel }: Props) {
  const buckets = bucketsOf(rows);
  return (
    <>
      <div className="bots-buckets" data-testid="bots-buckets">
        {BOTS_BUCKETS.map(b => {
          const list = buckets[b.level];
          return (
            <section key={b.level} className={`bots-bucket bots-bucket--${b.level}`} data-testid={`bots-bucket-${b.level}`}
              aria-label={`${b.title} · ${b.sub}`}>
              <header className="bots-bucket__head" {...tipProps(b.tip, `${b.title} · ${b.sub}`)}>
                <b>{b.title}</b>
                <span className="bots-bucket__sub">· {b.sub}</span>
                <span className="bots-bucket__count">{list.length}</span>
              </header>
              {b.level === 2 && !botOn && list.length ? (
                <p className="bots-bucket__note" data-testid="bots-bucket-bot-off">{BOTS_BUCKET_BOT_OFF}</p>
              ) : null}
              {list.length ? list.map(row => <Line key={row.id} row={row} why={why} onLevel={onLevel} />)
                : <p className="bots-bucket__empty">{BOTS_BUCKET_EMPTY[b.level]}</p>}
            </section>
          );
        })}
      </div>
      <p className="bots-buckets__rule" data-testid="bots-buckets-rule">{BOTS_BUCKETS_RULE}</p>
    </>
  );
}
