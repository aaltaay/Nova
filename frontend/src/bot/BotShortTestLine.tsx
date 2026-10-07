/**
 * A short setup's five-year test on its card (ADR 049 section 12): "Test: five-year test queued / running / passed /
 * failed", ahead of its read-out. The words are the backend's (`setup_scanner/short_tests.py`), read from the result
 * file the desk's harness writes; nothing here runs or judges a test. Until it passed on the rules in play, the
 * card's On stays locked.
 */
import {
  SHORT_TEST_LABEL,
  SHORT_TEST_STALE_TIP,
  SHORT_TEST_STATE_WORDS,
  SHORT_TEST_TIP,
} from '../constantGroups/short_setups';
import type { ShortTest } from '../setups';
import { tipProps } from '../ux/hoverTip';

function tipOf(test: ShortTest): string {
  const lines = [SHORT_TEST_TIP];
  const s = test.summary;
  if (s && s.trades != null) {
    const pf = s.pf != null ? ` · PF ${s.pf.toFixed(2)}` : '';
    const pf2 = s.pf_2x != null ? ` (${s.pf_2x.toFixed(2)} at twice the costs)` : '';
    const exp = s.exp_r != null ? ` · ${s.exp_r >= 0 ? '+' : '−'}${Math.abs(s.exp_r).toFixed(2)}R a trade` : '';
    const p = s.p != null ? ` · permutation p ${s.p.toFixed(3)}` : '';
    lines.push(`${s.trades} trades${pf}${pf2}${exp}${p}.`);
  }
  if (test.matches === false) lines.push(SHORT_TEST_STALE_TIP);
  if (test.file) lines.push(`Result file: ${test.file}`);
  return lines.join('\n');
}

export function BotShortTestLine({ setup, test }: { setup: string; test: ShortTest | null }) {
  if (!test) return null;
  const state = SHORT_TEST_STATE_WORDS[test.state] ? test.state : 'error';
  return (
    <p className={`bots-strat__test bots-strat__test--${state}`} data-testid={`bots-setup-test-${setup}`}
      {...tipProps(tipOf(test), 'The five-year test')}>
      <span className="bots-tbadge">{SHORT_TEST_LABEL}</span> {test.text}
    </p>
  );
}
