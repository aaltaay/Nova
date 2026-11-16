/** @vitest-environment jsdom */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { OWNER_COLORS, ownerHoldSentence } from '../constantGroups/owners';
import { fillHolders } from './accountLive';
import { threeBooksHistoryFixture } from './accountFixtures';
import { WhoseChip, WhoseChips, whoseWords } from './WhoseCell';

const whoseCss = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), './whose.css'), 'utf8');

afterEach(cleanup);

const chip = () => screen.getByTestId('account-whose');

describe('WhoseChip (ADR 072, mockup three-books v1 section 6)', () => {
  it('names each book in its own colour class', () => {
    render(<><WhoseChip owner="you" /><WhoseChip owner="claude" /><WhoseChip owner="brain" pill /></>);
    const [you, claude, brain] = screen.getAllByTestId('account-whose');
    expect([you.textContent, you.className]).toEqual(['You', 'acct-who is-you']);
    expect([claude.textContent, claude.className]).toEqual(['Claude', 'acct-who is-claude']);
    expect([brain.textContent, brain.className]).toEqual(['The brain', 'acct-who is-brain is-pill']);
  });

  it("names a retired bot inside Earlier bots", () => {
    render(<WhoseChip owner="earlier_bots" bot="live_trader" />);
    expect(chip().textContent).toBe('Earlier bots · Live Trader');
    expect(chip().className).toBe('acct-who is-earlier_bots');
  });

  it('says a trade you closed stays its trader\'s: "closed by you"', () => {
    render(<WhoseChip owner="brain" closedByYou />);
    expect(chip().textContent).toBe('The brain · closed by you');
    expect(chip().querySelector('em')?.className).toBe('is-by');
  });

  it("dashes a switched-off trader's open position, yours to close", () => {
    render(<WhoseChip owner="brain" handed />);
    expect(chip().textContent).toBe("The brain's · yours to close");
    expect(chip().className).toBe('acct-who is-brain is-handed');
  });

  it('never hands you your own shares; one of Nova\'s own closes reads Nova', () => {
    expect(whoseWords({ owner: 'you', handed: true, closedByYou: true })).toEqual({ main: 'You', sub: null, by: false });
    render(<WhoseChip owner={null} />);
    expect([chip().textContent, chip().className]).toEqual(['Nova', 'acct-who is-nova']);
  });

  it('draws one chip per holder a fill split across', () => {
    render(<WhoseChips tags={[{ owner: 'you' }, { owner: 'claude', closedByYou: true }]} />);
    expect(screen.getAllByTestId('account-whose').map((c) => c.textContent)).toEqual(['You', 'Claude · closed by you']);
  });
});

describe('whose a fill was', () => {
  it("reads each part's holder; a part you closed for Claude is Claude's, closed by you", () => {
    const fills = threeBooksHistoryFixture(1_790_000_000).fills;
    expect(fills.map((f) => fillHolders(f))).toEqual([
      [{ owner: 'earlier_bots', bot: 'live_trader', closedByYou: false }],
      [{ owner: 'earlier_bots', bot: 'live_trader', closedByYou: false }],
      [{ owner: 'you', bot: null, closedByYou: false }],
      [{ owner: 'you', bot: null, closedByYou: false }],
      [{ owner: 'claude', bot: null, closedByYou: false }],
      [{ owner: 'claude', bot: null, closedByYou: false }],
      [{ owner: 'claude', bot: null, closedByYou: false }],
      [{ owner: 'claude', bot: null, closedByYou: true }],
    ]);
  });

  it('falls back to the order\'s owner, and says nothing for a ledger without books', () => {
    const base = threeBooksHistoryFixture(1_790_000_000).fills[2];
    const { parts: _p, ...noParts } = base;
    expect(fillHolders({ ...noParts, owner: null, bot: null })).toEqual([{ owner: null, bot: null }]);
    const { owner: _o, bot: _b, ...legacy } = noParts;
    expect(fillHolders(legacy)).toBeUndefined();
  });
});

describe('the books\' colours', () => {
  it("whose.css's tokens are OWNER_COLORS: Claude coral, the brain purple, Earlier bots grey", () => {
    const token = (name: string) => whoseCss.match(new RegExp(`--nova-owner-${name}:\\s*(#[0-9a-f]{6})`, 'i'))?.[1];
    expect({ you: token('you'), claude: token('claude'), brain: token('brain'), earlier_bots: token('earlier') })
      .toEqual(OWNER_COLORS);
  });

  it('a refusal names whose the shares are', () => {
    expect(ownerHoldSentence('claude', 40)).toBe(" The 40 shares are Claude's -- switch Claude off to close them yourself.");
    expect(ownerHoldSentence('earlier_bots', -19)).toBe(" The 19 short is a retired bot's.");
  });
});
