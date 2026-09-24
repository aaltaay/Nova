/**
 * File an issue (approved mockup v2, 2026-09-24): Bug or Feature, an optional title and
 * description, the desk details and the diagnostics dump attached automatically (each can be
 * unticked, the dump previewed line by line), then File on GitHub. A floating card like What's
 * new; filing is one click with nothing typed. Every line posted is public, so the card says so.
 */
import { whyProps } from '../ux/whyTip';
import { typedIssueUrl, type IssueKind } from './issueApi';
import { openIssueLink, type IssueReport } from './useIssueReport';

const KINDS: { id: IssueKind; label: string; hint: string }[] = [
  { id: 'bug', label: 'Bug', hint: 'Something is wrong' },
  { id: 'feature', label: 'Feature', hint: 'Something I want Nova to do' },
];

function kb(bytes: number): string {
  return bytes >= 1024 ? `${Math.round(bytes / 1024)} KB` : `${bytes} B`;
}

function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

function Filed({ r }: { r: IssueReport }) {
  const f = r.filed;
  if (!f) return null;
  const dump = f.dump;
  return (
    <>
      <div className="nova-issue__body">
        <div className="nova-issue__filed">
          <span className="nova-issue__filed-mark" aria-hidden="true">✓</span>
          <div>
            <h2 className="nova-issue__title">Filed as #{f.number}</h2>
            <p className="nova-issue__subtitle">{f.title}</p>
          </div>
        </div>
        <ul className="nova-issue__steps">
          <li>Issue created on GitHub, labelled {f.kind === 'bug' ? 'bug' : 'enhancement'}</li>
          {dump?.url && <li>Dump uploaded as a secret gist and linked</li>}
          {dump && !dump.url && (
            <li className="nova-issue__step--warn">
              The dump was not uploaded ({dump.error ?? 'unknown error'})
              {dump.saved ? `; the issue names ${dump.fileName}, saved on this desk` : ''}
            </li>
          )}
          {(f.autoTitle || f.autoDescription) && <li>Nova wrote the {f.autoTitle && f.autoDescription ? 'title and description' : f.autoTitle ? 'title' : 'description'} from the dump</li>}
          <li>In the backlog inbox (00 - Untriaged) for the next triage</li>
        </ul>
      </div>
      <footer className="nova-issue__foot">
        {dump?.url ? (
          <button type="button" className="nova-issue__btn nova-issue__btn--quiet" onClick={() => openIssueLink(dump.url!)}>
            Open the dump
          </button>
        ) : (
          <span />
        )}
        <span className="nova-issue__actions">
          <button type="button" className="nova-issue__btn" onClick={() => openIssueLink(f.url)}>
            Open #{f.number}
          </button>
          <button type="button" className="nova-issue__btn nova-issue__btn--primary" onClick={r.close}>
            Done
          </button>
        </span>
      </footer>
    </>
  );
}

function Attachments({ r }: { r: IssueReport }) {
  const d = r.draft;
  const s = d?.dump.summary;
  const dumpLocked = !d;
  const dumpWhy = r.sample
    ? 'The sample desk has no desk to dump.'
    : r.draftLoading
      ? 'The dump is still being built.'
      : `The dump could not be built: ${r.draftError ?? 'unknown error'}`;
  const detailsWhy = r.sample
    ? 'The sample desk has no desk details.'
    : r.draftLoading
      ? 'Reading the desk…'
      : `The desk details could not be read: ${r.draftError ?? 'unknown error'}`;
  return (
    <div className="nova-issue__attach">
      <div className="nova-issue__attach-head">Attached automatically</div>
      <label className="nova-issue__att">
        <input
          type="checkbox"
          checked={r.attachDetails && !dumpLocked}
          disabled={dumpLocked}
          {...whyProps(dumpLocked, detailsWhy)}
          onChange={(e) => r.setAttachDetails(e.target.checked)}
        />
        <span>
          <b>Desk details</b>
          <span className="nova-issue__chips">
            {(d?.contextLines ?? []).map((line) => (
              <span key={line} className="nova-issue__chip">{line}</span>
            ))}
            {!d && <span className="nova-issue__muted">{r.draftLoading ? 'Reading the desk…' : 'Not available'}</span>}
          </span>
        </span>
      </label>
      <div className="nova-issue__att nova-issue__att--dump">
        <input
          id="nova-issue-dump"
          type="checkbox"
          checked={r.attachDump && !dumpLocked}
          disabled={dumpLocked}
          {...whyProps(dumpLocked, dumpWhy)}
          onChange={(e) => r.setAttachDump(e.target.checked)}
        />
        <div>
          <label htmlFor="nova-issue-dump">
            <b>Diagnostics dump</b> <span className="nova-issue__muted">— linked from the issue</span>
          </label>
          {r.draftLoading && <p className="nova-issue__muted">Building the dump…</p>}
          {!r.draftLoading && !d && !r.sample && (
            <p className="nova-issue__error">
              The dump could not be built: {r.draftError}{' '}
              <button type="button" className="nova-issue__link" onClick={() => void r.retryDraft()}>
                Try again
              </button>
            </p>
          )}
          {d && s && (
            <>
              <div className="nova-issue__file">
                <span aria-hidden="true">📄</span>
                <span className="nova-issue__file-name">{d.dump.fileName}</span>
                <span className="nova-issue__muted">{kb(d.dump.bytes)}</span>
              </div>
              <ul className="nova-issue__has">
                <li>
                  Desk checklist: {plural(s.rows, 'row')} (<span className="nova-issue__fail">{s.fail} fail</span>,{' '}
                  <span className="nova-issue__warn">{s.warn} warn</span>)
                  {s.checklistError && <span className="nova-issue__muted"> — unreadable: {s.checklistError}</span>}
                </li>
                <li>
                  Engine log: {plural(s.logRecords, 'recent warning or error', 'recent warnings and errors')}
                  {s.logError && <span className="nova-issue__muted"> — unreadable: {s.logError}</span>}
                </li>
                <li>{plural(s.clientErrors, 'error')} the desk windows reported</li>
                <li>{plural(s.windows, 'window')} open: page and symbol</li>
              </ul>
            </>
          )}
        </div>
        {d && (
          <button type="button" className="nova-issue__link" aria-expanded={r.preview.open} onClick={() => void r.togglePreview()}>
            {r.preview.open ? 'Hide' : 'Preview'}
          </button>
        )}
      </div>
      {r.preview.open && (
        <div className="nova-issue__preview" data-testid="issue-dump-preview">
          {r.preview.loading && <p className="nova-issue__muted">Loading the dump…</p>}
          {r.preview.error && <p className="nova-issue__error">{r.preview.error}</p>}
          {r.preview.text !== null && <pre>{r.preview.text}</pre>}
        </div>
      )}
    </div>
  );
}

function Form({ r }: { r: IssueReport }) {
  const d = r.draft;
  const bug = r.kind === 'bug';
  const showAuto = bug && !r.title.trim() && !r.details.trim() && r.attachDump && d?.autoTitle;
  const locked = r.lock !== null;
  const filer = d?.filer;
  // GitHub's own page: the backend's prefilled link, or -- when the desk itself did not answer -- what was typed.
  const fallback = r.error
    ? r.error.newIssueUrl ?? (r.error.reason ? null : typedIssueUrl(r.kind, r.title.trim(), r.details.trim()))
    : null;
  return (
    <>
      <div className="nova-issue__body">
        <div className="nova-issue__seg" role="radiogroup" aria-label="Kind">
          {KINDS.map((k) => (
            <button
              key={k.id}
              type="button"
              role="radio"
              aria-checked={r.kind === k.id}
              className="nova-issue__kind"
              data-kind={k.id}
              data-on={r.kind === k.id}
              onClick={() => r.setKind(k.id)}
            >
              <b>{k.label}</b>
              <small>{k.hint}</small>
            </button>
          ))}
        </div>

        <label className="nova-issue__label" htmlFor="nova-issue-title">
          Title <span>{bug ? 'optional' : 'a title or a line is needed'}</span>
        </label>
        <input
          id="nova-issue-title"
          className="nova-issue__input"
          value={r.title}
          maxLength={d?.titleMax ?? 120}
          placeholder={bug ? 'Leave empty and Nova titles it from the dump' : 'What should Nova do?'}
          onChange={(e) => r.setTitle(e.target.value)}
        />
        {showAuto && (
          <p className="nova-issue__auto">
            Will be filed as: <b>{d?.autoTitle}</b>
          </p>
        )}

        <label className="nova-issue__label" htmlFor="nova-issue-details">
          Description <span>optional</span>
        </label>
        <textarea
          id="nova-issue-details"
          className="nova-issue__input nova-issue__textarea"
          value={r.details}
          maxLength={d?.detailsMax ?? 8000}
          placeholder={
            bug
              ? 'What happened, what you expected. Leave empty and Nova describes it from the dump.'
              : 'What you want Nova to do, and why.'
          }
          onChange={(e) => r.setDetails(e.target.value)}
        />

        <Attachments r={r} />

        <div className="nova-issue__note">
          <span aria-hidden="true">🔒</span>
          <span>
            Built for a public page. Nova leaves out API keys, tokens, the PIN hash, IBKR account numbers, balances,
            file paths, your user and machine names, and IP addresses. <b>Preview</b> shows every line that goes out.
            Anything you type is public too.
          </span>
        </div>

        {r.error && (
          <div className="nova-issue__error nova-issue__error--box" role="alert">
            {r.error.message}
            {fallback && (
              <button type="button" className="nova-issue__link" onClick={() => openIssueLink(fallback)}>
                Open it on GitHub to finish
              </button>
            )}
          </div>
        )}
      </div>
      <footer className="nova-issue__foot">
        <span className="nova-issue__who">
          {filer?.direct ? (
            <>
              <span className="nova-issue__dot" aria-hidden="true" /> Files as <b>{filer.account}</b> · GitHub CLI on this PC
            </>
          ) : filer ? (
            <>
              <span className="nova-issue__dot nova-issue__dot--off" aria-hidden="true" /> {filer.reason}; Nova will open
              GitHub for you to finish
            </>
          ) : null}
        </span>
        <span className="nova-issue__actions">
          <button type="button" className="nova-issue__btn" onClick={r.close} disabled={r.phase === 'filing'}
            {...whyProps(r.phase === 'filing', 'Filing on GitHub…')}>
            Cancel
          </button>
          <button
            type="button"
            className="nova-issue__btn nova-issue__btn--primary"
            disabled={locked}
            {...whyProps(locked, r.lock)}
            onClick={() => void r.file()}
          >
            {r.phase === 'filing' ? 'Filing…' : 'File on GitHub'}
          </button>
        </span>
      </footer>
    </>
  );
}

export function IssueReportCard({ r }: { r: IssueReport }) {
  if (r.phase === 'closed') return null;
  return (
    <section className="nova-issue" aria-labelledby="nova-issue-heading" data-testid="issue-report" data-phase={r.phase}>
      {r.phase !== 'filed' && (
        <header className="nova-issue__head">
          <div>
            <h2 id="nova-issue-heading" className="nova-issue__title">File an issue</h2>
            <p className="nova-issue__subtitle">Goes straight to GitHub · {r.draft?.repo || 'aaltaay/Nova'}</p>
          </div>
          <button
            type="button"
            className="nova-issue__close"
            aria-label="Close File an issue"
            onClick={r.close}
            disabled={r.phase === 'filing'}
            {...whyProps(r.phase === 'filing', 'Filing on GitHub…')}
          >
            ×
          </button>
        </header>
      )}
      {r.phase === 'filed' ? <Filed r={r} /> : <Form r={r} />}
    </section>
  );
}
