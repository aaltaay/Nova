/**
 * The bot's notices as toasts (bot/botNoticeStore.ts, ADR 042's visibility rule): a
 * refused "Let the bot trade", Nova's entries cancelled when the desk left a venue, and
 * the daily loss limit's warning and trip (ADR 056, loss_limit/). Mounted once per
 * window with the symbol menu host, so a refusal raised from a pop-out shows in that
 * pop-out, and the loss limit's notices show in every window. A refusal or a trip stays
 * until dismissed; the rest leave after BOT_NOTICE_TTL_MS unless pointed at. The day
 * cover's alarm (bot/DayCoverAlarms.tsx, ADR 048 step 6) rides here too, so a short
 * Nova could not cover reaches every window.
 */
import { useEffect, useState, useSyncExternalStore } from 'react';
import { useLossLimitNotices } from '../loss_limit';
import { DayCoverAlarms } from './DayCoverAlarms';
import { dismissBotNotice, getBotNotices, pushBotNotice, subscribeBotNotices, type BotNotice } from './botNoticeStore';
import { useLiveTraderAskToasts } from './LiveTraderAsks';
import './botNotices.css';

const BOT_NOTICE_TTL_MS = 15_000;

function NoticeCard({ notice }: { notice: BotNotice }) {
  const [hover, setHover] = useState(false);
  const sticky = notice.tone === 'bad';
  useEffect(() => {
    if (hover || sticky) return undefined;
    const id = window.setTimeout(() => dismissBotNotice(notice.id), BOT_NOTICE_TTL_MS);
    return () => window.clearTimeout(id);
  }, [hover, sticky, notice.id]);
  return (
    <div className={`bot-notice bot-notice--${notice.tone}`} role={sticky ? 'alert' : 'status'}
      data-testid="bot-notice" data-tone={notice.tone}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <div className="bot-notice__text">
        <strong className="bot-notice__title">{notice.title}</strong>
        <span className="bot-notice__body">{notice.text}</span>
      </div>
      <button type="button" className="bot-notice__x" aria-label={`Dismiss: ${notice.title}`}
        data-testid="bot-notice-dismiss" onClick={() => dismissBotNotice(notice.id)}>×</button>
    </div>
  );
}

export function BotNotices() {
  useLossLimitNotices(pushBotNotice);
  const notices = useSyncExternalStore(subscribeBotNotices, getBotNotices, getBotNotices);
  const asks = useLiveTraderAskToasts();      // the Live Trader bot's asks (ADR 055) stack with the notices
  return (
    <>
      <DayCoverAlarms />
      {notices.length > 0 || asks.length > 0 ? (
        <div className="bot-notices" aria-label="Bot notices" data-testid="bot-notices">
          {asks}
          {notices.map(n => <NoticeCard key={n.id} notice={n} />)}
        </div>
      ) : null}
    </>
  );
}
