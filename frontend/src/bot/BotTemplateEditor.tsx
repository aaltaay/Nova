/**
 * A setup's parameters and templates (ADR 029): every number the setup runs
 * on, grouped as the scanner reads them, and the operator's named variations.
 * The built-in default is the pre-registered rules and stays locked -- New
 * copies it. Saving new rules on a template starts its evidence over (its own
 * read-out restarts), and the editor says so before it saves. Nothing here
 * places an order.
 */
import { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { BOT_SETUP_LABELS } from '../constantGroups/bot';
import {
  BOTS_TEMPLATE_BUILTIN_WHY,
  BOTS_TEMPLATE_DELETE_CONFIRM,
  BOTS_TEMPLATE_EVIDENCE_RESET,
  BOTS_TEMPLATE_IN_PLAY_WHY,
  BOTS_TEMPLATE_LIMIT_WHY,
  BOTS_TEMPLATE_NO_PARAMS,
  BOTS_TEMPLATE_NOTHING_CHANGED_WHY,
  BOTS_TEMPLATE_SAVING_WHY,
  BOTS_TEMPLATE_UNFIXED_WHY,
} from '../constantGroups/bots_page';
import { confirmApp, promptApp } from '../ux/appDialogApi';
import { BotParamField } from './BotParamField';
import { changedKeys, readoutText } from './templateFormat';
import { createTemplate, deleteTemplate, playTemplate, updateTemplate } from './templatesApi';
import { TemplateApiError, type ParamValue, type SetupTemplate, type SetupTemplates } from './templateTypes';

interface Props {
  open: boolean;
  setup: SetupTemplates | null;
  maxPerSetup: number;
  onClose: () => void;
  /** A write's answer: the setup as it now stands. */
  onApply: (setup: SetupTemplates) => void;
}

function stamp(ts: number | null): string {
  return ts ? new Date(ts * 1000).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
}

export function BotTemplateEditor({ open, setup, maxPerSetup, onClose, onApply }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, ParamValue>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [serverField, setServerField] = useState<{ key: string; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selected: SetupTemplate | null = useMemo(() => {
    if (!setup) return null;
    return setup.templates.find(t => t.id === selectedId) ?? setup.templates.find(t => t.id === setup.in_play)
      ?? setup.templates[0] ?? null;
  }, [setup, selectedId]);

  useEffect(() => {
    if (!open) return;
    setSelectedId(setup?.in_play ?? null);
    setError(null);
    // Opening for another setup starts on its template in play.
  }, [open, setup?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setDraft(selected ? { ...selected.values } : {});
    setFieldErrors({});
    setServerField(null);
  }, [selected?.id, selected?.rev, selected?.fingerprint]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!setup) return null;
  const label = BOT_SETUP_LABELS[setup.id] ?? setup.id;
  const groups = setup.catalogue.groups;
  const dirty = selected ? changedKeys(selected.values, draft) : [];
  const invalid = Object.values(fieldErrors).some(Boolean);
  const atLimit = setup.templates.length >= maxPerSetup;
  const lockedWhy = !selected ? null : selected.builtin ? BOTS_TEMPLATE_BUILTIN_WHY : busy ? BOTS_TEMPLATE_SAVING_WHY : null;

  async function run(action: () => Promise<SetupTemplates>, select?: (s: SetupTemplates) => string | null) {
    setBusy(true);
    setError(null);
    setServerField(null);
    try {
      const next = await action();
      onApply(next);
      if (select) setSelectedId(select(next));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (err instanceof TemplateApiError && err.field && draft[err.field] !== undefined) {
        setServerField({ key: err.field, message });
      } else setError(message);
    } finally {
      setBusy(false);
    }
  }

  async function onNew() {
    if (!selected) return;
    const name = await promptApp({ title: `New ${label} template`, message: `A copy of "${selected.name}" to change.`,
      placeholder: `${selected.name} (copy)` });
    if (!name?.trim() || !setup) return;
    const before = new Set(setup.templates.map(t => t.id));
    void run(() => createTemplate(setup.id, { name: name.trim(), from: selected.id }),
      next => next.templates.find(t => !before.has(t.id))?.id ?? null);
  }

  async function onRename() {
    if (!selected || !setup) return;
    const name = await promptApp({ title: 'Rename template', message: `A new name for "${selected.name}".`,
      placeholder: selected.name });
    if (!name?.trim()) return;
    void run(() => updateTemplate(setup.id, selected.id, { name: name.trim() }));
  }

  async function onDelete() {
    if (!selected || !setup) return;
    const ok = await confirmApp({ title: 'Delete template', message: BOTS_TEMPLATE_DELETE_CONFIRM(selected.name),
      confirmLabel: 'Delete', tone: 'danger' });
    if (!ok) return;
    void run(() => deleteTemplate(setup.id, selected.id), next => next.in_play);
  }

  async function onSave() {
    if (!selected || !setup || dirty.length === 0) return;
    const scored = selected.readout?.go_triggered ?? 0;
    if (setup.scanner) {
      const ok = await confirmApp({ title: 'Save new rules', message: BOTS_TEMPLATE_EVIDENCE_RESET(selected.name, selected.rev, scored),
        confirmLabel: 'Save', tone: 'warning' });
      if (!ok) return;
    }
    const values = Object.fromEntries(dirty.map(k => [k, draft[k]]));
    void run(() => updateTemplate(setup.id, selected.id, { values }));
  }

  const saveWhy = busy ? BOTS_TEMPLATE_SAVING_WHY : invalid ? BOTS_TEMPLATE_UNFIXED_WHY
    : dirty.length === 0 ? BOTS_TEMPLATE_NOTHING_CHANGED_WHY : null;
  const playWhy = !selected ? null : selected.in_play ? BOTS_TEMPLATE_IN_PLAY_WHY
    : selected.error ? `${selected.name} no longer validates -- fix it first` : busy ? BOTS_TEMPLATE_SAVING_WHY : null;
  const editWhy = !selected ? null : selected.builtin ? BOTS_TEMPLATE_BUILTIN_WHY : busy ? BOTS_TEMPLATE_SAVING_WHY : null;
  const newWhy = atLimit ? BOTS_TEMPLATE_LIMIT_WHY(maxPerSetup) : busy ? BOTS_TEMPLATE_SAVING_WHY : null;

  return (
    <Dialog open={open} onOpenChange={next => { if (!next) onClose(); }}>
      <DialogContent className="bots-tpl border-border bg-card text-card-foreground sm:max-w-[1040px]" data-testid="bots-template-editor">
        <DialogHeader>
          <DialogTitle>{label} — parameters and templates</DialogTitle>
          <DialogDescription>{setup.catalogue.source}</DialogDescription>
        </DialogHeader>
        {groups.length === 0 ? (
          <p className="bots-tpl__empty" data-testid="bots-template-empty">{BOTS_TEMPLATE_NO_PARAMS}</p>
        ) : (
          <div className="bots-tpl__body">
            <aside className="bots-tpl__list" aria-label="Templates">
              <ul>
                {setup.templates.map(t => (
                  <li key={t.id}>
                    <button type="button" className={`bots-tpl__item${t.id === selected?.id ? ' is-on' : ''}`}
                      data-testid={`bots-template-${t.id}`} onClick={() => setSelectedId(t.id)}>
                      <b>{t.name}</b>
                      <span>
                        {t.in_play ? <em className="bots-badge">in play</em> : null}
                        {t.builtin ? 'locked' : `rev ${t.rev}`}
                        {readoutText(t) ? ` · ${readoutText(t)}` : ''}
                      </span>
                      {t.error ? <small className="bots-tpl__bad">{t.error}</small> : null}
                    </button>
                  </li>
                ))}
              </ul>
              <div className="bots-tpl__listacts">
                <button type="button" className="bots-btn" data-testid="bots-template-new" disabled={newWhy != null}
                  data-why={newWhy ?? undefined} onClick={() => void onNew()}>+ New from this</button>
                <button type="button" className="bots-btn" data-testid="bots-template-play" disabled={playWhy != null}
                  data-why={playWhy ?? undefined}
                  onClick={() => { if (selected) void run(() => playTemplate(setup.id, selected.id)); }}>Put in play</button>
                <button type="button" className="bots-btn" data-testid="bots-template-rename" disabled={editWhy != null}
                  data-why={editWhy ?? undefined} onClick={() => void onRename()}>Rename</button>
                <button type="button" className="bots-btn bots-btn--danger" data-testid="bots-template-delete"
                  disabled={editWhy != null} data-why={editWhy ?? undefined} onClick={() => void onDelete()}>Delete</button>
              </div>
            </aside>
            <div className="bots-tpl__params">
              {selected ? (
                <p className="bots-tpl__meta" data-testid="bots-template-meta">
                  <b>{selected.name}</b> · {selected.builtin ? 'the pre-registered rules, locked' : `rev ${selected.rev}`}
                  {selected.updated_at ? ` · saved ${stamp(selected.updated_at)}` : ''}
                  {selected.readout?.reason ? ` · ${selected.readout.reason}` : ''}
                </p>
              ) : null}
              {groups.map(g => (
                <fieldset key={g.id} className="bots-tpl__group" data-testid={`bots-template-group-${g.id}`}>
                  <legend>{g.label}</legend>
                  <p className="bots-muted">{g.blurb}</p>
                  {g.params.map(spec => (
                    <BotParamField key={spec.key} spec={spec} value={draft[spec.key] ?? null} lockedWhy={lockedWhy}
                      serverError={serverField?.key === spec.key ? serverField.message : null}
                      onChange={(key, value, fieldError) => {
                        setDraft(prev => ({ ...prev, [key]: value }));
                        setFieldErrors(prev => ({ ...prev, [key]: fieldError ?? '' }));
                        if (serverField?.key === key) setServerField(null);
                      }} />
                  ))}
                </fieldset>
              ))}
            </div>
          </div>
        )}
        {error ? <p className="bots-hero__error" role="alert" data-testid="bots-template-error">{error}</p> : null}
        {groups.length > 0 ? (
          <div className="bots-tpl__foot">
            <span className="bots-muted">{dirty.length ? `${dirty.length} change${dirty.length === 1 ? '' : 's'} not saved` : ''}</span>
            <button type="button" className="bots-btn" data-testid="bots-template-discard" disabled={dirty.length === 0 || busy}
              data-why={dirty.length === 0 || busy ? (busy ? BOTS_TEMPLATE_SAVING_WHY : BOTS_TEMPLATE_NOTHING_CHANGED_WHY) : undefined}
              onClick={() => { if (selected) setDraft({ ...selected.values }); setFieldErrors({}); }}>Discard</button>
            <button type="button" className="bots-btn bots-btn--primary" data-testid="bots-template-save"
              disabled={saveWhy != null} data-why={saveWhy ?? undefined} onClick={() => void onSave()}>Save rules</button>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
