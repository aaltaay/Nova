import { BOT_ALLOWLIST_STRIP_TITLE } from '../constantGroups/bot';
import { BotAllowlistEditor } from './BotAllowlistEditor';
import { useBotAllowlist } from './useBotAllowlist';

export function StrategyAllowlistCard() {
  const { symbols, add, remove } = useBotAllowlist();

  return (
    <section className="bot-strategy__card" data-testid="bot-strategy-allowlist">
      <h3>{BOT_ALLOWLIST_STRIP_TITLE}</h3>
      <BotAllowlistEditor
        testId="bot-strategy-allowlist"
        symbols={symbols}
        add={add}
        remove={remove}
      />
    </section>
  );
}
