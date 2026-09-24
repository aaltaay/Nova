/**
 * The issue form's state: opening builds a fresh draft (the dump the operator previews is the
 * one uploaded), filing posts it, and what was typed survives a refusal. Title and description
 * are optional for a bug (operator decision, 2026-09-24): with nothing typed the backend writes
 * both from the dump. The sample desk never asks the backend for anything.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import {
  fetchDumpText,
  fetchIssueDraft,
  fileIssue,
  IssueApiError,
  type IssueDraft,
  type IssueFiled,
  type IssueKind,
} from './issueApi';
import { onIssueFormOpen } from './issueFormBus';

export type IssuePhase = 'closed' | 'form' | 'filing' | 'filed';

export interface IssuePreview {
  open: boolean;
  loading: boolean;
  text: string | null;
  error: string | null;
}

const CLOSED_PREVIEW: IssuePreview = { open: false, loading: false, text: null, error: null };

function message(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  return 'The desk could not be reached';
}

/** Why File on GitHub cannot be pressed now, or null when it can. */
export function fileLockReason(p: {
  sample: boolean;
  phase: IssuePhase;
  kind: IssueKind;
  title: string;
  details: string;
  attachDump: boolean;
  draft: IssueDraft | null;
  draftLoading: boolean;
}): string | null {
  if (p.sample) return SAMPLE_WRITE_REFUSAL;
  if (p.phase === 'filing') return 'Filing on GitHub…';
  const words = Boolean(p.title.trim() || p.details.trim());
  if (p.kind === 'feature' && !words) return 'Say what you want Nova to do: a title or one line is enough.';
  if (p.attachDump && p.draftLoading) return 'The dump is still being built.';
  const dump = p.attachDump && p.draft !== null;
  if (!words && !dump) return 'Type a line, or attach the dump: an empty report says nothing.';
  if (p.draft && p.title.trim().length > p.draft.titleMax) return `The title is longer than ${p.draft.titleMax} characters.`;
  if (p.draft && p.details.trim().length > p.draft.detailsMax) {
    return `The description is longer than ${p.draft.detailsMax} characters.`;
  }
  return null;
}

/** Open a link the form shows: through the desktop app's allowlist, else a new browser tab. */
export function openIssueLink(url: string): void {
  const updates = typeof window !== 'undefined' ? window.novaDesktop?.updates : undefined;
  if (updates) {
    updates
      .act({ action: 'open-link', url })
      .then((reply) => {
        if (!reply?.ok) console.warn('[nova] issue link refused', url, reply?.error);
      })
      .catch((err: unknown) => console.warn('[nova] issue link failed', url, err));
    return;
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}

export function useIssueReport() {
  const [phase, setPhase] = useState<IssuePhase>('closed');
  const phaseRef = useRef<IssuePhase>('closed');
  const [draft, setDraft] = useState<IssueDraft | null>(null);
  const [draftLoading, setDraftLoading] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [kind, setKindState] = useState<IssueKind>('bug');
  const [title, setTitle] = useState('');
  const [details, setDetails] = useState('');
  const [attachDetails, setAttachDetails] = useState(true);
  const [attachDump, setAttachDump] = useState(true);
  const [error, setError] = useState<IssueApiError | null>(null);
  const [filed, setFiled] = useState<IssueFiled | null>(null);
  const [preview, setPreview] = useState<IssuePreview>(CLOSED_PREVIEW);
  const [sample] = useState(onSampleDesk);
  const loadSeq = useRef(0);

  const go = useCallback((next: IssuePhase) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);

  const loadDraft = useCallback(async () => {
    const seq = ++loadSeq.current;
    setDraftLoading(true);
    setDraftError(null);
    setPreview(CLOSED_PREVIEW);
    try {
      const next = await fetchIssueDraft();
      if (seq === loadSeq.current) setDraft(next);
    } catch (err) {
      if (seq === loadSeq.current) {
        setDraft(null);
        setDraftError(message(err));
      }
    } finally {
      if (seq === loadSeq.current) setDraftLoading(false);
    }
  }, []);

  const open = useCallback(() => {
    const current = phaseRef.current;
    if (current === 'form' || current === 'filing') return;
    // A new report after a filed one starts empty; a closed draft keeps what was typed.
    if (current === 'filed') {
      setTitle('');
      setDetails('');
      setKindState('bug');
      setAttachDump(true);
      setFiled(null);
    }
    setError(null);
    go('form');
    if (!sample) void loadDraft();
  }, [go, loadDraft, sample]);

  useEffect(() => onIssueFormOpen(open), [open]);

  const close = useCallback(() => {
    if (phaseRef.current === 'filing') return;
    loadSeq.current += 1;
    setDraftLoading(false);
    setPreview(CLOSED_PREVIEW);
    go('closed');
  }, [go]);

  const setKind = useCallback((next: IssueKind) => {
    setKindState(next);
    // A dump rarely helps a feature request; a bug report starts with it.
    setAttachDump(next === 'bug');
  }, []);

  const togglePreview = useCallback(async () => {
    if (preview.open) {
      setPreview((p) => ({ ...p, open: false }));
      return;
    }
    if (!draft) return;
    if (preview.text !== null) {
      setPreview((p) => ({ ...p, open: true }));
      return;
    }
    setPreview({ open: true, loading: true, text: null, error: null });
    try {
      const text = await fetchDumpText(draft.draftId);
      setPreview({ open: true, loading: false, text, error: null });
    } catch (err) {
      setPreview({ open: true, loading: false, text: null, error: message(err) });
    }
  }, [draft, preview.open, preview.text]);

  const file = useCallback(async () => {
    if (sample || phaseRef.current === 'filing') return;
    go('filing');
    setError(null);
    try {
      const done = await fileIssue({
        kind,
        title: title.trim(),
        details: details.trim(),
        context: attachDetails ? draft?.context ?? null : null,
        draftId: draft?.draftId ?? null,
        attachDump: attachDump && draft !== null,
      });
      setFiled(done);
      go('filed');
    } catch (err) {
      const refusal = err instanceof IssueApiError ? err : new IssueApiError(message(err));
      setError(refusal);
      go('form');
      if (refusal.reason === 'ISSUE_DRAFT_EXPIRED') void loadDraft();
    }
  }, [attachDetails, attachDump, details, draft, go, kind, loadDraft, sample, title]);

  const lock = fileLockReason({ sample, phase, kind, title, details, attachDump, draft, draftLoading });

  return {
    phase,
    draft,
    draftLoading,
    draftError,
    kind,
    title,
    details,
    attachDetails,
    attachDump,
    error,
    filed,
    preview,
    sample,
    lock,
    open,
    close,
    setKind,
    setTitle,
    setDetails,
    setAttachDetails,
    setAttachDump,
    togglePreview,
    file,
    retryDraft: loadDraft,
  };
}

export type IssueReport = ReturnType<typeof useIssueReport>;
