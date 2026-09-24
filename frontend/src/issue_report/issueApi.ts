/**
 * The desk's issue API (backend/issue_report/, schema in AGENTS.md §3 "Filing an issue from
 * the desk"): a fresh draft with its dump, the dump's text for Preview, and the filing.
 * Every answer passes one shape gate; a draft that does not parse is an error, never half-read.
 */
import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import { ISSUE_NEW_URL, ISSUE_SCHEMA_VERSION, ISSUE_URL_BODY_MAX } from './issueConstants';

export type IssueKind = 'bug' | 'feature';

export interface IssueContext {
  [key: string]: string | null;
}

export interface DumpSummary {
  rows: number;
  fail: number;
  warn: number;
  logRecords: number;
  clientErrors: number;
  windows: number;
  checklistError: string | null;
  logError: string | null;
}

export interface IssueDraft {
  draftId: string;
  repo: string;
  filer: { direct: boolean; account: string | null; reason: string | null };
  context: IssueContext | null;
  contextLines: string[];
  titleMax: number;
  detailsMax: number;
  autoTitle: string;
  dump: { fileName: string; bytes: number; summary: DumpSummary; sections: string[] };
}

export interface IssueFiled {
  number: number;
  url: string;
  title: string;
  kind: IssueKind;
  autoTitle: boolean;
  autoDescription: boolean;
  dump: { fileName: string; url: string | null; error: string | null; saved: boolean } | null;
}

export interface IssueForm {
  kind: IssueKind;
  title: string;
  details: string;
  context: IssueContext | null;
  draftId: string | null;
  attachDump: boolean;
}

export class IssueApiError extends Error {
  readonly reason: string | null;
  readonly field: string | null;
  readonly newIssueUrl: string | null;

  constructor(message: string, reason: string | null = null, field: string | null = null, newIssueUrl: string | null = null) {
    super(message);
    this.reason = reason;
    this.field = field;
    this.newIssueUrl = newIssueUrl;
  }
}

type Raw = Record<string, unknown>;

function obj(v: unknown): Raw | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Raw) : null;
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

function strOrNull(v: unknown): string | null {
  return typeof v === 'string' && v ? v : null;
}

function num(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

export function readDraft(value: unknown): IssueDraft | null {
  const raw = obj(value);
  const dump = obj(raw?.dump);
  const summary = obj(dump?.summary);
  const filer = obj(raw?.filer);
  const limits = obj(raw?.limits);
  if (!raw || raw.schema_version !== ISSUE_SCHEMA_VERSION || !str(raw.draft_id) || !dump || !summary || !filer) {
    return null;
  }
  const context = obj(raw.context);
  return {
    draftId: str(raw.draft_id),
    repo: str(raw.repo),
    filer: { direct: filer.direct === true, account: strOrNull(filer.account), reason: strOrNull(filer.reason) },
    context: context
      ? Object.fromEntries(Object.entries(context).map(([k, v]) => [k, typeof v === 'string' ? v : null]))
      : null,
    contextLines: Array.isArray(raw.context_lines) ? raw.context_lines.filter((l): l is string => typeof l === 'string') : [],
    titleMax: num(limits?.title_max) || 120,
    detailsMax: num(limits?.details_max) || 8000,
    autoTitle: str(raw.auto_title),
    dump: {
      fileName: str(dump.file_name),
      bytes: num(dump.bytes),
      sections: Array.isArray(dump.sections) ? dump.sections.filter((s): s is string => typeof s === 'string') : [],
      summary: {
        rows: num(summary.rows),
        fail: num(summary.fail),
        warn: num(summary.warn),
        logRecords: num(summary.log_records),
        clientErrors: num(summary.client_errors),
        windows: num(summary.windows),
        checklistError: strOrNull(summary.checklist_error),
        logError: strOrNull(summary.log_error),
      },
    },
  };
}

export function readFiled(value: unknown): IssueFiled | null {
  const raw = obj(value);
  const number = Number(raw?.number);
  if (!raw || !Number.isInteger(number) || number <= 0 || !str(raw.url)) return null;
  const dump = obj(raw.dump);
  return {
    number,
    url: str(raw.url),
    title: str(raw.title),
    kind: raw.kind === 'feature' ? 'feature' : 'bug',
    autoTitle: raw.auto_title === true,
    autoDescription: raw.auto_description === true,
    dump: dump
      ? { fileName: str(dump.file_name), url: strOrNull(dump.url), error: strOrNull(dump.error), saved: dump.saved === true }
      : null,
  };
}

async function refusal(res: Response): Promise<IssueApiError> {
  const body = obj(await res.json().catch(() => null));
  const detail = obj(body?.detail);
  if (detail) {
    return new IssueApiError(
      str(detail.error) || `The desk answered ${res.status}`,
      strOrNull(detail.reason),
      strOrNull(detail.field),
      strOrNull(detail.new_issue_url),
    );
  }
  const text = typeof body?.detail === 'string' ? body.detail : '';
  return new IssueApiError(text || `The desk answered ${res.status}`);
}

export async function fetchIssueDraft(): Promise<IssueDraft> {
  const res = await novaFetch(`${API_URL}/issues/draft`);
  if (!res.ok) throw await refusal(res);
  const draft = readDraft(await res.json().catch(() => null));
  if (!draft) throw new IssueApiError('The desk answered with a draft this window cannot read — reload Nova');
  return draft;
}

export async function fetchDumpText(draftId: string): Promise<string> {
  const res = await novaFetch(`${API_URL}/issues/draft/${encodeURIComponent(draftId)}/dump`);
  if (!res.ok) throw await refusal(res);
  return res.text();
}

export async function fileIssue(form: IssueForm): Promise<IssueFiled> {
  const res = await novaFetch(`${API_URL}/issues`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      schema_version: ISSUE_SCHEMA_VERSION,
      kind: form.kind,
      title: form.title,
      details: form.details,
      context: form.context,
      draft_id: form.draftId,
      attach_dump: form.attachDump,
    }),
  });
  if (!res.ok) throw await refusal(res);
  const filed = readFiled(await res.json().catch(() => null));
  if (!filed) {
    throw new IssueApiError(
      "GitHub may have the issue, but the desk's answer was unreadable — check the repository's issues before filing again",
    );
  }
  return filed;
}

/** GitHub's new-issue page with what was typed -- for when the desk cannot be reached at all. */
export function typedIssueUrl(kind: IssueKind, title: string, details: string): string {
  const body = details.length > ISSUE_URL_BODY_MAX ? `${details.slice(0, ISSUE_URL_BODY_MAX)}\n\n(cut to fit the link)` : details;
  const params = new URLSearchParams({ title, body, labels: kind === 'bug' ? 'bug' : 'enhancement' });
  return `${ISSUE_NEW_URL}?${params.toString().replace(/\+/g, '%20')}`;
}
