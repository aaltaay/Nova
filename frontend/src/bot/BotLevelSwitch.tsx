/**
 * A strategy's own Off · Eyes · On (ADR 042, ADR 044): one switch, drawn on its card and on its row in the
 * buckets above the cards. Every setup with a scanner may be at any level; a short's On waits on its five-year
 * test (ADR 049) and says so -- the lock and its reason ride on the On button (`data-why`). Owner of the switch
 * only; the levels and their words are `constantGroups/bot.ts`'s.
 */
import { BOT_STRATEGY_LEVEL_LABELS as BOT_LEVEL_LABELS, BOT_SETUP_LEVEL_TIPS } from '../constantGroups/bot';
import { tipProps } from '../ux/hoverTip';

const LEVELS = [0, 1, 2] as const;

interface Props {
  id: string;
  label: string;
  own: 0 | 1 | 2;
  /** Why every level is locked now (saving, an older API); null when it is not. */
  why: string | null;
  /** Why On is locked (a short whose test has not passed); null when it is not. */
  onLock: string | null;
  onLevel: (id: string, level: number) => void;
  /** The test id's prefix: the card's switch and the bucket row's are two controls. */
  testPrefix?: string;
}

export function BotLevelSwitch({ id, label, own, why, onLock, onLevel, testPrefix = 'bots-setup-level' }: Props) {
  return (
    <span className="bots-levels" role="radiogroup" aria-label={`${label} level`}>
      {LEVELS.map(n => {
        // On stays reachable from On itself (to go down), never into it while its test locks it.
        const lock = why ?? (n === 2 && onLock && own !== 2 ? onLock : null);
        return (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={own === n}
            className={`bots-levels__opt${own === n ? ' is-on' : ''}${n === 2 && onLock ? ' is-locked' : ''}`}
            data-testid={`${testPrefix}-${id}-${n}`}
            disabled={lock != null}
            data-why={lock ?? undefined}
            {...(lock ? {} : tipProps(BOT_SETUP_LEVEL_TIPS[n], `${BOT_LEVEL_LABELS[n]} · ${label}`))}
            onClick={() => { if (own !== n) onLevel(id, n); }}
          >
            {n === 2 && onLock ? '🔒 ' : ''}{BOT_LEVEL_LABELS[n]}
          </button>
        );
      })}
    </span>
  );
}
