import { describe, expect, it } from 'vitest';
import { GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP } from '../constantGroups/global_bar';
import type { IbkrAccountSummary } from '../ibkr/types';
import {
  accountClassOf,
  accountStructureLabel,
  accountTypeTooltip,
  headerAccountPillView,
  type HeaderAccountPillStatus,
} from './headerAccountPill';

function status(overrides: Partial<HeaderAccountPillStatus> = {}): HeaderAccountPillStatus {
  return {
    connected: true,
    account_id: 'U1234567',
    account_ids: ['U1234567'],
    broker_account_kind: 'live',
    ...overrides,
  };
}

function summary(overrides: Partial<IbkrAccountSummary> = {}): IbkrAccountSummary {
  return { connected: true, mode: 'live', ...overrides };
}

describe('headerAccountPillView -- Live (the IBKR account)', () => {
  it('reads "Individual Margin (U1234567)" from AccountType, account_class and the full id', () => {
    const view = headerAccountPillView({
      venue: 'live',
      status: status(),
      summary: summary({ AccountType: 'INDIVIDUAL', account_class: 'margin', TradingType: 'STKNOPT' }),
    });
    expect(view?.label).toBe('Individual Margin (U1234567)');
    expect(view?.kind).toBe('live');
    expect(view?.structure).toBe('Individual');
    expect(view?.accountClass).toBe('margin');
    expect(view?.id).toBe('U1234567');
    expect(view?.accounts).toEqual([{ id: 'U1234567', active: true }]);
    expect(view?.tooltip).toContain('IBKR account U1234567 (LIVE)');
    expect(view?.tooltip).toContain('login username is never exposed');
    expect(view?.tooltip).toContain(GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP);
    expect(view?.tooltip).toContain('IBKR AccountType: INDIVIDUAL');
    expect(view?.tooltip).toContain('IBKR TradingType-S: STKNOPT');
    expect(view?.note).toMatch(/IB Gateway/);
  });

  it('says Cash for a stamped cash account', () => {
    const view = headerAccountPillView({
      venue: 'live',
      status: status(),
      summary: summary({ AccountType: 'INDIVIDUAL', account_class: 'cash' }),
    });
    expect(view?.label).toBe('Individual Cash (U1234567)');
    expect(view?.accountClass).toBe('cash');
  });

  it('omits a structure it does not know and a class that is not stamped -- never a guess', () => {
    // MARGIN is a class token, not ownership: no structure word, class from the stamp.
    expect(
      headerAccountPillView({
        venue: 'live',
        status: status(),
        summary: summary({ AccountType: 'MARGIN', account_class: 'margin' }),
      })?.label,
    ).toBe('Margin (U1234567)');
    // INDIVIDUAL with BP ~ cash but no stamp: the old chip inferred Cash; the pill says nothing.
    const bare = headerAccountPillView({
      venue: 'live',
      status: status(),
      summary: summary({ AccountType: 'INDIVIDUAL', TradingType: 'STKNOPT', BuyingPower: 376, TotalCashValue: 383 }),
    });
    expect(bare?.label).toBe('Individual (U1234567)');
    expect(bare?.accountClass).toBeNull();
    expect(bare?.tooltip).toContain('IBKR AccountType: INDIVIDUAL');
    expect(bare?.tooltip).not.toMatch(/\bMargin\b/);
    // Nothing reported at all: the id alone, with the raw type stated as missing.
    const idOnly = headerAccountPillView({ venue: 'live', status: status(), summary: summary() });
    expect(idOnly?.label).toBe('U1234567');
    expect(idOnly?.tooltip).toContain('IBKR AccountType: (missing)');
  });

  it('shows the id alone while the account snapshot is still loading', () => {
    const view = headerAccountPillView({ venue: 'live', status: status(), summary: null });
    expect(view?.label).toBe('U1234567');
    expect(view?.structure).toBeNull();
    expect(view?.accountClass).toBeNull();
  });

  it('classifies DU… as paper and lists the other managed accounts with the active one marked', () => {
    const view = headerAccountPillView({
      venue: 'live',
      status: status({
        account_id: 'DUQ266899',
        account_ids: ['DUQ266899', 'DUQ111111'],
        broker_account_kind: 'paper',
      }),
      summary: null,
    });
    expect(view?.kind).toBe('paper');
    expect(view?.tooltip).toContain('IBKR account DUQ266899 (paper)');
    expect(view?.tooltip).toContain('Other managed accounts on this login: DUQ111111');
    expect(view?.accounts).toEqual([
      { id: 'DUQ266899', active: true },
      { id: 'DUQ111111', active: false },
    ]);
  });

  it('lists the active id even when account_ids omits it', () => {
    const view = headerAccountPillView({
      venue: 'live',
      status: status({ account_ids: [] }),
      summary: null,
    });
    expect(view?.accounts).toEqual([{ id: 'U1234567', active: true }]);
  });

  it('is null while disconnected or with nothing to say -- an old id would be a lie', () => {
    expect(headerAccountPillView({ venue: 'live', status: status({ connected: false }), summary: null })).toBeNull();
    expect(
      headerAccountPillView({
        venue: 'live',
        status: status({ account_id: null, account_ids: [] }),
        summary: null,
      }),
    ).toBeNull();
    expect(
      headerAccountPillView({
        venue: 'disconnected',
        status: status({ connected: false, account_id: 'U1234567' }),
        summary: summary({ AccountType: 'INDIVIDUAL', account_class: 'margin' }),
      }),
    ).toBeNull();
  });
});

describe('headerAccountPillView -- practice venues (ADR 020)', () => {
  it('NOVA-PAPER reads as Nova Paper Margin, Nova-managed, fake money, not IBKR', () => {
    const view = headerAccountPillView({
      venue: 'paper',
      status: status({ account_id: 'NOVA-PAPER', account_ids: ['NOVA-PAPER'] }),
      // Paper runs on the live Gateway, so an IBKR summary exists beside the ledger.
      summary: summary({ AccountType: 'INDIVIDUAL', account_class: 'cash' }),
      practiceId: 'NOVA-PAPER',
    });
    expect(view?.label).toBe('Nova Paper Margin (NOVA-PAPER)');
    expect(view?.kind).toBe('practice');
    expect(view?.id).toBe('NOVA-PAPER');
    expect(view?.tooltip).toMatch(/Nova-managed/);
    expect(view?.tooltip).toMatch(/fake money/i);
    expect(view?.tooltip).not.toMatch(/IBKR account NOVA-PAPER/);
    expect(view?.accounts).toEqual([{ id: 'NOVA-PAPER', active: true }]);
    expect(view?.note).toMatch(/only account/);
  });

  it('NOVA-SIM reads as Nova Sim Margin and its tooltip names the replay', () => {
    const view = headerAccountPillView({
      venue: 'sim',
      status: status({ account_id: 'NOVA-SIM', account_ids: ['NOVA-SIM'] }),
      summary: null,
    });
    expect(view?.label).toBe('Nova Sim Margin (NOVA-SIM)');
    expect(view?.kind).toBe('practice');
    expect(view?.tooltip).toMatch(/replay/);
  });

  it('states the practice id from the venue before the ledger or status report it', () => {
    const view = headerAccountPillView({
      venue: 'paper',
      status: status({ connected: false, account_id: null, account_ids: [] }),
      summary: null,
    });
    expect(view?.label).toBe('Nova Paper Margin (NOVA-PAPER)');
  });
});

describe('structure / class / raw-type helpers', () => {
  it('maps known IBKR ownership types and omits the rest', () => {
    expect(accountStructureLabel('INDIVIDUAL')).toBe('Individual');
    expect(accountStructureLabel(' individual ')).toBe('Individual');
    expect(accountStructureLabel('IRA')).toBe('IRA');
    expect(accountStructureLabel('MARGIN')).toBeNull();
    expect(accountStructureLabel('')).toBeNull();
    expect(accountStructureLabel(null)).toBeNull();
  });

  it('takes the class only from a connected, stamped snapshot', () => {
    expect(accountClassOf(summary({ account_class: 'margin' }))).toBe('margin');
    expect(accountClassOf(summary({ account_class: null }))).toBeNull();
    expect(accountClassOf({ connected: false, mode: 'disconnected', account_class: 'margin' })).toBeNull();
    expect(accountClassOf(null)).toBeNull();
  });

  it('keeps the raw AccountType and TradingType in the tooltip', () => {
    expect(accountTypeTooltip(summary({ AccountType: 'cash' }))).toContain('IBKR AccountType: cash');
    expect(accountTypeTooltip(summary())).toContain('IBKR AccountType: (missing)');
    expect(accountTypeTooltip(summary({ TradingType: 'STKNOPT' }))).toContain('IBKR TradingType-S: STKNOPT');
    expect(accountTypeTooltip(summary())).toMatch(/IBKR_SHORT_ENABLED/);
  });
});
