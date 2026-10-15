/**
 * "Live Traders · TraderTV" at the top of the TraderTV LIVE page (ADR 055 and its 2026-10-15 amendment, mockup v1
 * approved 2026-10-14; reached through the bot barrel's lazy `LiveTradersPanel`): one card per host the
 * TraderTV bar shows, each a bot of its own -- Paper only, never Live. Above the cards, one line says what stops
 * every host's bot now (the desk off Paper, the Bot switch off, Freeze all orders, the feed), so no blocker is
 * silent. A desk with no TraderTV feed says so in one line.
 */
import { useState } from 'react';
import {
  LT_ANCHOR,
  LT_FEED_OFF,
  LT_LOADING,
  LT_NO_HOSTS,
  LT_PAPER_CHIP,
  LT_SUB,
  LT_SUB_TIP,
  LT_TITLE,
} from '../constantGroups/live_trader';
import { tipProps } from '../ux';
import { prose } from './botsPageFormat';
import { answerLiveTraderAsk, patchLiveTrader } from './liveTraderApi';
import { useLiveTraders } from './liveTraderStore';
import { LiveTraderHostCard } from './LiveTraderHostCard';
import type { LtAsk, LtPatch } from './liveTraderTypes';
import './botsPage.css';
import './botsOnePage.css';
import './liveTraders.css';

export function BotLiveTradersCard() {
  const { view, error, apply, refresh } = useLiveTraders();
  const [busy, setBusy] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<string | null>(null);

  async function write(name: string, run: () => Promise<Parameters<typeof apply>[0]>) {
    setBusy(name);
    setWriteError(null);
    try {
      apply(await run());
    } catch (err) {
      setWriteError(err instanceof Error ? err.message : String(err));
      void refresh();
    } finally {
      setBusy(null);
    }
  }
  const onPatch = (name: string, body: LtPatch) => write(name, () => patchLiveTrader(name, body));
  const onAnswer = (name: string, ask: LtAsk, approve: boolean) =>
    write(name, () => answerLiveTraderAsk(name, ask.id, approve));

  const blocker = view && view.enabled && !view.can_trade.ok ? view.can_trade.why : null;
  return (
    <section className="bots-card lt-card" id={LT_ANCHOR} data-testid="bots-live-traders">
      <div className="bots-card__head lt-card__head">
        <h3>{LT_TITLE}</h3>
        <span className="bots-card__sub" {...tipProps(LT_SUB_TIP, LT_TITLE)}>{LT_SUB}</span>
        <span className="lt-chip lt-chip--paper">{LT_PAPER_CHIP}</span>
      </div>
      {!view ? <p className="lt-muted" role="status">{error ? prose(error) : LT_LOADING}</p> : null}
      {view && !view.enabled ? <p className="lt-muted" data-testid="lt-feed-off">{LT_FEED_OFF}</p> : null}
      {view?.settings_error || view?.book_error ? (
        <p className="lt-warn is-bad" role="alert">{prose(view.settings_error || view.book_error || '')}</p>
      ) : null}
      {blocker ? <p className="lt-warn" data-testid="lt-blocker">{prose(blocker)}</p> : null}
      {writeError ? <p className="lt-warn is-bad" role="alert" data-testid="lt-error">{prose(writeError)}</p> : null}
      {view && view.enabled && view.hosts.length === 0 ? <p className="lt-muted">{LT_NO_HOSTS}</p> : null}
      {view && view.hosts.length ? (
        <div className="lt-grid">
          {view.hosts.map(host => (
            <LiveTraderHostCard key={host.name} host={host} sellAllAt={view.sell_all_at} busy={busy === host.name}
              onPatch={onPatch} onAnswer={onAnswer} />
          ))}
        </div>
      ) : null}
    </section>
  );
}
