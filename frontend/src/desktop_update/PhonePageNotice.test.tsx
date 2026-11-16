/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PhonePageNotice, phonePageNotice } from './PhonePageNotice';
import type { PhonePage } from './updateView';

const OK: PhonePage = { root: 'C:\\Nova', build: 'current', served: true, last: null };

describe('the phone page notice', () => {
  it('says nothing while the phone has the desk\'s page and it is served, or while a start is coming up', () => {
    expect(phonePageNotice(OK)).toBeNull();
    expect(phonePageNotice({ ...OK, build: 'building' })).toBeNull();
    expect(phonePageNotice({ ...OK, served: false, last: { at: 1, outcome: 'started', text: 'Started' } })).toBeNull();
  });

  it('says a failed build in plain words, with the reason, and that Nova tries again', () => {
    const model = phonePageNotice({ ...OK, build: 'failed', last: { at: 1, outcome: 'failed', text: 'npm install failed' } });
    expect(model?.text).toContain('did not rebuild');
    expect(model?.hint).toContain('npm install failed');
    expect(model?.hint).toContain('tries again');
  });

  it('says a server that did not come up', () => {
    const model = phonePageNotice({ ...OK, served: false, last: { at: 1, outcome: 'failed', text: 'did not answer' } });
    expect(model?.text).toContain('server is not running');
  });

  it('Later hides it', () => {
    render(<PhonePageNotice phonePage={{ ...OK, build: 'failed', last: { at: 1, outcome: 'failed', text: 'x' } }} />);
    expect(screen.getByTestId('phone-page-notice')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Later' }));
    expect(screen.queryByTestId('phone-page-notice')).toBeNull();
  });
});
