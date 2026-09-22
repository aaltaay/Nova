/**
 * Right top -- Components as Webull's vertical ring list: Realized,
 * Unrealized, Commissions, SEC + FINRA fees and Bot share of P&L, each ring
 * the share of the absolute total so a 0% fee ring is not read as "no fees".
 */
import {
  ACCOUNT_COMPONENTS_FOOT,
  ACCOUNT_COMPONENTS_NOTE,
  ACCOUNT_COMPONENTS_TITLE,
  ACCOUNT_COMP_BOT,
  ACCOUNT_COMP_COMMISSIONS,
  ACCOUNT_COMP_FEES,
  ACCOUNT_COMP_FEES_NOTE,
  ACCOUNT_COMP_REALIZED,
  ACCOUNT_COMP_UNREALIZED,
  ACCOUNT_COMP_UNREALIZED_NOTE,
  accountCompBotShare,
  accountCompCommissions,
  accountCompRoundTrips,
  type AccountRange,
} from '../constantGroups/account_page';
import { formatSignedMoney } from '../components/globalBarMoney';
import { PanelHead, Ring, toneClass, type Tone } from './accountBits';
import { botIds, componentRings, sellCount, type ComponentRing } from './accountFigures';
import type { PracticeHistory } from './accountHistoryTypes';

interface Props {
  history: PracticeHistory | null;
  absence: string | null;
  range: AccountRange;
}

function labelOf(ring: ComponentRing, history: PracticeHistory): { k: string; s: string } {
  const fills = history.fills;
  switch (ring.id) {
    case 'realized':
      return { k: ACCOUNT_COMP_REALIZED, s: accountCompRoundTrips(sellCount(fills)) };
    case 'unrealized':
      return { k: ACCOUNT_COMP_UNREALIZED, s: ACCOUNT_COMP_UNREALIZED_NOTE };
    case 'commissions':
      return { k: ACCOUNT_COMP_COMMISSIONS, s: accountCompCommissions(fills.length) };
    case 'fees':
      return { k: ACCOUNT_COMP_FEES, s: ACCOUNT_COMP_FEES_NOTE };
    case 'bot': {
      const ids = botIds(fills);
      const pct = fills.some((f) => f.source === 'bot' || f.bot_id != null) ? Math.round(ring.share * 100) : null;
      return { k: ACCOUNT_COMP_BOT, s: `${ids.length ? `${ids.join(', ')} · ` : ''}${accountCompBotShare(pct)}` };
    }
  }
}

export function ComponentsPanel({ history, absence, range }: Props) {
  return (
    <section className="acct-panel acct-panel--comp" data-testid="account-components" aria-label={ACCOUNT_COMPONENTS_TITLE}>
      <PanelHead title={`${ACCOUNT_COMPONENTS_TITLE} · ${range}`}>
        <span>{ACCOUNT_COMPONENTS_NOTE}</span>
      </PanelHead>
      {!history ? (
        <div className="acct-absent" data-testid="account-components-absent">{absence}</div>
      ) : (
        <div className="acct-comp">
          {componentRings(history.components, history.fills).map((ring) => {
            const { k, s } = labelOf(ring, history);
            const tone: Tone = ring.tone;
            const none = ring.id === 'bot' && ring.share === 0 && !history.fills.some((f) => f.source === 'bot' || f.bot_id != null);
            return (
              <div key={ring.id} className="acct-crow" data-testid={`account-comp-${ring.id}`}>
                <Ring share={ring.share} tone={tone} size={42} testId={`account-comp-ring-${ring.id}`} />
                <div className="acct-crow__k">{k}<small>{s}</small></div>
                <div className={`acct-crow__v acct-num ${none ? 'acct-muted' : toneClass(tone === 'bot' ? (ring.value > 0 ? 'up' : ring.value < 0 ? 'down' : 'flat') : tone)}`}>
                  {none ? 'none' : formatSignedMoney(ring.value)}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <p className="acct-foot">{ACCOUNT_COMPONENTS_FOOT}</p>
    </section>
  );
}
