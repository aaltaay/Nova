/**
 * @vitest-environment jsdom
 *
 * The template editor (ADR 029): every parameter, the default locked and saying
 * why, a new template from it, new rules saved only after the evidence warning,
 * and a refusal shown at the field it names.
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BOTS_TEMPLATE_BUILTIN_WHY, BOTS_TEMPLATE_NOTHING_CHANGED_WHY } from '../constantGroups/bots_page';
import { templatesPayload } from './botsPageFixtures';
import { BotTemplateEditor } from './BotTemplateEditor';
import { TemplateApiError, type SetupTemplate, type SetupTemplates } from './templateTypes';

const api = vi.hoisted(() => ({
  createTemplate: vi.fn(),
  updateTemplate: vi.fn(),
  deleteTemplate: vi.fn(),
  playTemplate: vi.fn(),
}));
vi.mock('./templatesApi', () => api);
const dialogs = vi.hoisted(() => ({ confirmApp: vi.fn(), promptApp: vi.fn(), alertApp: vi.fn() }));
vi.mock('../ux/appDialogApi', () => dialogs);

function fp(): SetupTemplates {
  return templatesPayload().setups.find(s => s.id === 'first_pullback')!;
}

function withMine(setup: SetupTemplates, patch: Partial<SetupTemplate> = {}): SetupTemplates {
  const base = setup.templates[0];
  const mine: SetupTemplate = { ...base, id: 't-mine', name: 'Low float', builtin: false, in_play: false, rev: 1,
    values: { ...base.values, max_float_m: 10 }, ...patch };
  return { ...setup, templates: [...setup.templates, mine] };
}

async function flush() {
  await act(async () => { await Promise.resolve(); });
}

describe('BotTemplateEditor', () => {
  let onApply: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onApply = vi.fn();
    Object.values(api).forEach(fn => fn.mockReset());
    Object.values(dialogs).forEach(fn => fn.mockReset());
  });
  afterEach(() => cleanup());

  function open(setup: SetupTemplates) {
    return render(<BotTemplateEditor open setup={setup} maxPerSetup={6} onClose={() => undefined} onApply={onApply} />);
  }

  it('lists every parameter group, and the default is locked with the reason', () => {
    open(fp());
    for (const g of ['stock', 'setup', 'entry', 'risk', 'tape', 'grade', 'bot']) {
      expect(screen.getByTestId(`bots-template-group-${g}`)).toBeTruthy();
    }
    const leg = screen.getByTestId('bots-param-leg_pct') as HTMLInputElement;
    expect(leg.value).toBe('5');
    expect(leg.disabled).toBe(true);
    expect(leg.getAttribute('data-why')).toBe(BOTS_TEMPLATE_BUILTIN_WHY);
    expect(screen.getByTestId('bots-template-save').getAttribute('data-why')).toBe(BOTS_TEMPLATE_NOTHING_CHANGED_WHY);
    expect(screen.getByTestId('bots-template-delete').getAttribute('data-why')).toBe(BOTS_TEMPLATE_BUILTIN_WHY);
    expect(screen.getByTestId('bots-template-play').getAttribute('data-why')).toBe('Already in play');
  });

  it('makes a new template from the one shown and selects it', async () => {
    const next = withMine(fp());
    dialogs.promptApp.mockResolvedValue('Low float');
    api.createTemplate.mockResolvedValue(next);
    open(fp());
    await act(async () => { fireEvent.click(screen.getByTestId('bots-template-new')); });
    await flush();
    expect(api.createTemplate).toHaveBeenCalledWith('first_pullback', { name: 'Low float', from: 'default' });
    expect(onApply).toHaveBeenCalledWith(next);
  });

  it('saves only the changed rules, after saying the evidence starts over', async () => {
    const setup = withMine(fp());
    dialogs.confirmApp.mockResolvedValue(true);
    api.updateTemplate.mockResolvedValue(setup);
    open(setup);
    fireEvent.click(screen.getByTestId('bots-template-t-mine'));
    const leg = screen.getByTestId('bots-param-leg_pct') as HTMLInputElement;
    expect(leg.disabled).toBe(false);
    fireEvent.change(leg, { target: { value: '7' } });
    expect(within(screen.getByTestId('bots-param-row-leg_pct')).getByText(/default 5%/)).toBeTruthy();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-template-save')); });
    await flush();
    expect(dialogs.confirmApp.mock.calls[0][0].message).toMatch(/starts its evidence over/);
    expect(api.updateTemplate).toHaveBeenCalledWith('first_pullback', 't-mine', { values: { leg_pct: 7 } });
  });

  it('shows the backend refusal at the field it names', async () => {
    const setup = withMine(fp());
    dialogs.confirmApp.mockResolvedValue(true);
    api.updateTemplate.mockRejectedValue(new TemplateApiError('the arming window ends before it starts', 'entry_cutoff'));
    open(setup);
    fireEvent.click(screen.getByTestId('bots-template-t-mine'));
    fireEvent.change(screen.getByTestId('bots-param-session_start'), { target: { value: '12:00' } });
    await act(async () => { fireEvent.click(screen.getByTestId('bots-template-save')); });
    await flush();
    expect(within(screen.getByTestId('bots-param-row-entry_cutoff')).getByRole('alert').textContent)
      .toMatch(/ends before it starts/);
  });

  it('refuses a bad value locally before any request', () => {
    open(withMine(fp()));
    fireEvent.click(screen.getByTestId('bots-template-t-mine'));
    fireEvent.change(screen.getByTestId('bots-param-leg_window'), { target: { value: '2.5' } });
    expect(within(screen.getByTestId('bots-param-row-leg_window')).getByRole('alert').textContent).toMatch(/whole number/);
    expect((screen.getByTestId('bots-template-save') as HTMLButtonElement).disabled).toBe(true);
  });

  it('puts another template in play', async () => {
    const setup = withMine(fp());
    api.playTemplate.mockResolvedValue(setup);
    open(setup);
    fireEvent.click(screen.getByTestId('bots-template-t-mine'));
    await act(async () => { fireEvent.click(screen.getByTestId('bots-template-play')); });
    await flush();
    expect(api.playTemplate).toHaveBeenCalledWith('first_pullback', 't-mine');
  });

  it('says a setup with no test has no parameters yet', () => {
    open(templatesPayload().setups.find(s => s.id === 'micro_pullback')!);
    expect(screen.getByTestId('bots-template-empty').textContent).toMatch(/never been tested/);
  });
});
