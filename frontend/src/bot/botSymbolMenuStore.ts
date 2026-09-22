/** One floating allowlist menu for scanner rows + trader tabs. */
export type BotSymbolMenuTab = {
  /** Whether the tab that opened the menu is pinned (preview tabs, ADR 011). */
  pinned: boolean;
  onTogglePin: () => void;
};

export type BotSymbolMenuOpen = {
  symbol: string;
  x: number;
  y: number;
  /** Present only when a Trader tab opened the menu: adds Pin / Unpin. */
  tab?: BotSymbolMenuTab;
} | null;

let current: BotSymbolMenuOpen = null;
const listeners = new Set<(value: BotSymbolMenuOpen) => void>();

function publish(value: BotSymbolMenuOpen): void {
  current = value;
  listeners.forEach(listener => listener(value));
}

export function openBotSymbolMenu(symbol: string, x: number, y: number, tab?: BotSymbolMenuTab): void {
  const next = symbol.trim().toUpperCase();
  if (!next) return;
  publish(tab ? { symbol: next, x, y, tab } : { symbol: next, x, y });
}

export function closeBotSymbolMenu(): void {
  publish(null);
}

export function getBotSymbolMenu(): BotSymbolMenuOpen {
  return current;
}

export function subscribeBotSymbolMenu(
  listener: (value: BotSymbolMenuOpen) => void,
): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
