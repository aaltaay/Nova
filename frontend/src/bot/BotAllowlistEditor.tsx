import { useState } from 'react';
import {
  BOT_ALLOWLIST_ADD_BUTTON,
  BOT_ALLOWLIST_ADD_LABEL,
  BOT_ALLOWLIST_CHIP_REMOVE,
  BOT_ALLOWLIST_EMPTY,
  BOT_ALLOWLIST_HINT,
  BOT_SYMBOL_ALLOWLIST_CAP,
} from '../constantGroups/bot';
import { BOTS_SYMBOLS_CAP_WHY } from '../constantGroups/bots_page';

export type BotAllowlistMutator = (symbol: string) => Promise<unknown> | unknown;

type Props = {
  testId: string;
  symbols: string[];
  add: BotAllowlistMutator;
  remove: BotAllowlistMutator;
};

export function BotAllowlistEditor({ testId, symbols, add, remove }: Props) {
  const [draft, setDraft] = useState('');
  const atCap = symbols.length >= BOT_SYMBOL_ALLOWLIST_CAP;

  async function onAdd() {
    const ticker = draft.trim();
    if (!ticker || atCap) return;
    await add(ticker);
    setDraft('');
  }

  return (
    <>
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
                data-testid={`${testId}-remove-${sym}`}
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
            data-testid={`${testId}-input`}
            value={draft}
            autoComplete="off"
            spellCheck={false}
            disabled={atCap}
            data-why={atCap ? BOTS_SYMBOLS_CAP_WHY(BOT_SYMBOL_ALLOWLIST_CAP) : undefined}
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
          data-testid={`${testId}-add`}
          disabled={atCap}
          data-why={atCap ? BOTS_SYMBOLS_CAP_WHY(BOT_SYMBOL_ALLOWLIST_CAP) : undefined}
          onClick={() => void onAdd()}
        >
          {BOT_ALLOWLIST_ADD_BUTTON}
        </button>
      </div>
    </>
  );
}
