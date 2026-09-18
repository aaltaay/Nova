import { useState } from 'react';
import {
  BOT_ALLOWLIST_ADD_BUTTON,
  BOT_ALLOWLIST_ADD_LABEL,
  BOT_ALLOWLIST_CHIP_REMOVE,
  BOT_ALLOWLIST_EMPTY,
  BOT_ALLOWLIST_HINT,
} from '../constantGroups/bot';
import { useBotAllowlist } from './useBotAllowlist';

export function StrategyAllowlistCard() {
  const { symbols, add, remove } = useBotAllowlist();
  const [draft, setDraft] = useState('');

  async function onAdd() {
    const ticker = draft.trim();
    if (!ticker) return;
    await add(ticker);
    setDraft('');
  }

  return (
    <section className="bot-strategy__card" data-testid="bot-strategy-allowlist">
      <h3>Symbol allowlist</h3>
      <p className="form-hint">{BOT_ALLOWLIST_HINT}</p>
      {symbols.length === 0 ? (
        <p className="form-hint">{BOT_ALLOWLIST_EMPTY}</p>
      ) : (
        <ul className="bot-strategy__chips">
          {symbols.map(sym => (
            <li key={sym}>
              <span>{sym}</span>
              <button
                type="button"
                data-testid={`bot-strategy-allowlist-remove-${sym}`}
                onClick={() => void remove(sym)}
              >
                {BOT_ALLOWLIST_CHIP_REMOVE}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="bot-strategy__add">
        <label>
          {BOT_ALLOWLIST_ADD_LABEL}
          <input
            data-testid="bot-strategy-allowlist-input"
            value={draft}
            autoComplete="off"
            spellCheck={false}
            onChange={event => setDraft(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Enter') {
                event.preventDefault();
                void onAdd();
              }
            }}
          />
        </label>
        <button
          type="button"
          data-testid="bot-strategy-allowlist-add"
          onClick={() => void onAdd()}
        >
          {BOT_ALLOWLIST_ADD_BUTTON}
        </button>
      </div>
    </section>
  );
}
