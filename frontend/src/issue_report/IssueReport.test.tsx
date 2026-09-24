/**
 * @vitest-environment jsdom
 *
 * File an issue: one click files a bug with nothing typed; a feature needs words; the dump is
 * previewed before it goes; a refusal keeps what was typed and offers GitHub's own page.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readDraft, readFiled, typedIssueUrl } from './issueApi';
import { openIssueForm } from './issueFormBus';
import { IssueReportHost } from './IssueReportHost';

const DRAFT = {
  schema_version: 1,
  repo: 'aaltaay/Nova',
  public: true,
  filer: { direct: true, via: 'gh', account: 'aaltaay', reason: null },
  kinds: [],
  context: { nova: 'v991', commit: 'dc0e346a', ui: null, venue: 'paper', page: 'trader', tab: null, symbol: 'GCTK' },
  context_lines: ['Nova v991 (dc0e346a)', 'Venue: Paper', 'Page: Trader · GCTK'],
  limits: { title_max: 120, details_max: 8000 },
  draft_id: 'd1',
  created_at: 1790262318,
  auto_title: 'Desk report: Gateway API port — live port 4001 refused (Trader · GCTK, 11:05 ET)',
  dump: {
    file_name: 'nova-dump-2026-09-24-1105.txt',
    bytes: 43000,
    sections: [],
    summary: { rows: 30, fail: 1, warn: 4, log_records: 50, client_errors: 0, windows: 1, removed: 17 },
  },
};

const FILED = {
  schema_version: 1,
  number: 612,
  url: 'https://github.com/aaltaay/Nova/issues/612',
  kind: 'bug',
  title: DRAFT.auto_title,
  labels: ['bug'],
  auto_title: true,
  auto_description: true,
  removed: 0,
  dump: { file_name: DRAFT.dump.file_name, url: 'https://gist.github.com/aaltaay/0123456789abcdef0123', error: null, saved: true },
  via: 'gh',
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

let fetchMock: ReturnType<typeof vi.fn>;
let posted: Record<string, unknown>[];

beforeEach(() => {
  posted = [];
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).endsWith('/issues/draft')) return json(DRAFT);
    if (String(url).endsWith('/issues/draft/d1/dump')) return new Response('Nova desk dump -- 2026-09-24\n[FAIL] Gateway');
    if (String(url).endsWith('/issues') && init?.method === 'POST') {
      posted.push(JSON.parse(String(init.body)));
      return json(FILED, 201);
    }
    return json({ detail: 'not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function openForm() {
  render(<IssueReportHost />);
  act(() => openIssueForm());
  await screen.findByText('nova-dump-2026-09-24-1105.txt');
}

describe('the issue form', () => {
  it('renders nothing until it is asked for', () => {
    render(<IssueReportHost />);
    expect(screen.queryByTestId('issue-report')).toBeNull();
  });

  it('files a bug in one click with nothing typed: Nova titles it from the dump', async () => {
    await openForm();
    expect(screen.getByText(/Will be filed as:/).textContent).toContain('Desk report: Gateway API port');
    expect(screen.getByText('Page: Trader · GCTK')).toBeTruthy();
    expect(screen.getByText(/Files as/).textContent).toContain('aaltaay');
    fireEvent.click(screen.getByRole('button', { name: 'File on GitHub' }));
    await screen.findByText('Filed as #612');
    expect(posted[0]).toEqual({
      schema_version: 1,
      kind: 'bug',
      title: '',
      details: '',
      context: DRAFT.context,
      draft_id: 'd1',
      attach_dump: true,
    });
    expect(screen.getByText('Nova wrote the title and description from the dump')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Open the dump' })).toBeTruthy();
  });

  it('a feature needs words, and says so on the locked button', async () => {
    await openForm();
    fireEvent.click(screen.getByRole('radio', { name: /Feature/ }));
    const file = screen.getByRole('button', { name: 'File on GitHub' }) as HTMLButtonElement;
    expect(file.disabled).toBe(true);
    expect(file.getAttribute('data-why')).toContain('Say what you want Nova to do');
    expect((screen.getAllByRole('checkbox')[1] as HTMLInputElement).checked).toBe(false);
    fireEvent.change(screen.getByLabelText(/Title/), { target: { value: 'Flatten-all hot key' } });
    expect(file.disabled).toBe(false);
  });

  it('an empty bug without the dump says nothing, so it cannot be filed', async () => {
    await openForm();
    fireEvent.click(screen.getAllByRole('checkbox')[1]);
    const file = screen.getByRole('button', { name: 'File on GitHub' });
    expect(file.getAttribute('data-why')).toContain('an empty report says nothing');
  });

  it('previews the exact dump before it goes', async () => {
    await openForm();
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    const preview = await screen.findByTestId('issue-dump-preview');
    await waitFor(() => expect(preview.textContent).toContain('[FAIL] Gateway'));
  });

  it('a refusal keeps what was typed and offers GitHub’s prefilled page', async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (String(url).endsWith('/issues/draft')) return json(DRAFT);
      if (init?.method === 'POST') {
        return json({ detail: { reason: 'ISSUE_FILER_UNAVAILABLE', error: 'the GitHub CLI on this PC is not signed in',
          field: null, new_issue_url: 'https://github.com/aaltaay/Nova/issues/new?title=x' } }, 503);
      }
      return json({}, 404);
    });
    await openForm();
    fireEvent.change(screen.getByLabelText(/Description/), { target: { value: 'Chart froze' } });
    fireEvent.click(screen.getByRole('button', { name: 'File on GitHub' }));
    expect((await screen.findByRole('alert')).textContent).toContain('not signed in');
    expect((screen.getByLabelText(/Description/) as HTMLTextAreaElement).value).toBe('Chart froze');
    const open = vi.fn();
    vi.stubGlobal('open', open);
    fireEvent.click(screen.getByRole('button', { name: 'Open it on GitHub to finish' }));
    expect(open).toHaveBeenCalledWith('https://github.com/aaltaay/Nova/issues/new?title=x', '_blank', 'noopener,noreferrer');
  });
});

describe('the issue API shapes', () => {
  it('reads a draft and refuses another schema', () => {
    expect(readDraft(DRAFT)?.dump.summary.fail).toBe(1);
    expect(readDraft({ ...DRAFT, schema_version: 2 })).toBeNull();
    expect(readFiled(FILED)?.dump?.url).toContain('gist.github.com');
    expect(readFiled({ ...FILED, number: 0 })).toBeNull();
  });

  it('builds GitHub’s new-issue link from what was typed', () => {
    const url = typedIssueUrl('feature', 'Hot key', 'a b');
    expect(url).toBe('https://github.com/aaltaay/Nova/issues/new?title=Hot%20key&body=a%20b&labels=enhancement');
  });
});
