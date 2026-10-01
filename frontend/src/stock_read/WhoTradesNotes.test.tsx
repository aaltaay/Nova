/**
 * @vitest-environment jsdom
 *
 * Who trades keeps Level 2's room without hiding a reason (ADR 042): the first three notes, warnings
 * first, on their own lines; the rest in one "+N more" line that names them on hover and opens them.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { NotesList } from './WhoTradesRow';

afterEach(cleanup);

const notes = [
  { id: 'window', tone: 'info', text: 'Every bot window is closed now.' },
  { id: 'not_active', tone: 'warn', text: 'The bot is not active: press Activate on the Bots page.' },
  { id: 'no_depth', tone: 'warn', text: 'Nova holds no Level 2 line for APUS.' },
  { id: 'daily_cap', tone: 'warn', text: "Nova's one automatic buy today is used." },
  { id: 'not_followed', tone: 'info', text: 'The scanner does not follow APUS.' },
] as const;

describe('Who trades notes', () => {
  it('shows three, warnings first, and folds the rest into one line that names them', () => {
    render(<NotesList notes={[...notes]} sym="APUS" />);
    const shown = screen.getAllByRole('listitem').map(li => li.textContent);
    expect(shown.slice(0, 3)).toEqual([notes[1].text, notes[2].text, notes[3].text]);
    const more = screen.getByTestId('who-trades-notes-more');
    expect(more.textContent).toMatch(/^\+2 more reasons/);
    expect(more.getAttribute('data-tip')).toBe(`${notes[0].text}\n${notes[4].text}`);
  });

  it('opens every reason on a click, and folds them again', () => {
    render(<NotesList notes={[...notes]} sym="APUS" />);
    fireEvent.click(screen.getByTestId('who-trades-notes-more'));
    for (const n of notes) expect(screen.getByTestId(`who-trades-note-${n.id}`).textContent).toBe(n.text);
    fireEvent.click(screen.getByTestId('who-trades-notes-less'));
    expect(screen.queryByTestId('who-trades-note-window')).toBeNull();
  });

  it('shows up to three without a fold line', () => {
    render(<NotesList notes={[...notes.slice(0, 3)]} sym="APUS" />);
    expect(screen.queryByTestId('who-trades-notes-more')).toBeNull();
  });
});
