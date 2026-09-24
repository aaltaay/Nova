/**
 * Release notes the desk shows -- pure: no Electron, no I/O.
 *
 * Each vNNN GitHub Release carries one hidden line tools/release_notes.py writes
 * from the commit that made it (schema in AGENTS.md §3):
 *
 *   <!-- nova-release-notes {"schema_version":1,"tag":"v976","title":...} -->
 *
 * This reads it out of GitHub's Releases API rows, picks the releases between
 * two installed versions (the update notice: what the new one adds; What's new:
 * what the last update brought), and writes the plain text a native dialog shows.
 * A release without the line (made before release notes existed) is listed with
 * `recorded: false`, never an invented summary.
 */
import { releaseTagFromText } from './releaseTag.mjs';

export const RELEASES_REPO = 'aaltaay/Nova';
/** One page is enough: a desk more than 100 releases behind is told the rest are on GitHub. */
export const RELEASES_PER_PAGE = 100;
export const RELEASES_API_URL = `https://api.github.com/repos/${RELEASES_REPO}/releases?per_page=${RELEASES_PER_PAGE}`;
export const RELEASES_PAGE_URL = `https://github.com/${RELEASES_REPO}/releases`;
export const RELEASE_NOTES_SCHEMA_VERSION = 1;
/** The update notice and What's new list at most this many releases; the rest are counted. */
export const RELEASE_NOTES_MAX_LISTED = 30;
/** Help > What's New: the installed release and the ones just before it. */
export const RECENT_RELEASES_LISTED = 10;
const NOTES_TEXT_MAX_CHARS = 1200;
const TEXT_MAX = 600;
const POINTS_MAX = 8;

const MARKER_RE = /<!--\s*nova-release-notes\s+(\{[\s\S]*?\})\s*-->/;
const TAG_RE = /^v(\d+)$/;
const RELEASE_LINK_RE = new RegExp(
  `^https://github\\.com/${RELEASES_REPO.replace('/', '\\/')}/(?:releases(?:/tag/v\\d+)?|pull/\\d+)$`,
);

/** `v976` -> 976; anything else -> null. */
export function tagNumber(tag) {
  const match = TAG_RE.exec(String(tag ?? '').trim());
  return match ? Number(match[1]) : null;
}

/** An app version (`0.1.976`) or a tag (`v976`) as the release number, or null. */
export function releaseNumber(versionOrTag) {
  return tagNumber(releaseTagFromText(versionOrTag));
}

/** Only this repo's release and PR pages open from the notes. */
export function isReleaseLink(url) {
  return RELEASE_LINK_RE.test(String(url ?? ''));
}

function text(value, max = TEXT_MAX) {
  if (typeof value !== 'string') return '';
  const clean = value.replace(/\s+/g, ' ').trim();
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean;
}

/** The record in a release body, or null when it has none or it is not one we read. */
export function parseNotesRecord(body) {
  const match = MARKER_RE.exec(String(body ?? ''));
  if (!match) return null;
  let raw;
  try {
    raw = JSON.parse(match[1]);
  } catch {
    return null;
  }
  if (!raw || raw.schema_version !== RELEASE_NOTES_SCHEMA_VERSION) return null;
  const pr = Number(raw.pr);
  return {
    title: text(raw.title, 200),
    kind: text(raw.kind, 20) || null,
    scope: text(raw.scope, 40) || null,
    pr: Number.isInteger(pr) && pr > 0 ? pr : null,
    summary: text(raw.summary),
    points: Array.isArray(raw.points) ? raw.points.map((p) => text(p, 200)).filter(Boolean).slice(0, POINTS_MAX) : [],
  };
}

/** One GitHub Releases API row as the desk lists it, or null for anything that is not a published vNNN release. */
export function releaseEntry(row) {
  if (!row || row.draft || row.prerelease) return null;
  const tag = String(row.tag_name ?? '');
  const number = tagNumber(tag);
  if (number == null) return null;
  const record = parseNotesRecord(row.body);
  const url = isReleaseLink(row.html_url) ? row.html_url : `${RELEASES_PAGE_URL}/tag/${tag}`;
  return {
    tag,
    number,
    recorded: Boolean(record),
    title: record?.title || '',
    kind: record?.kind ?? null,
    scope: record?.scope ?? null,
    pr: record?.pr ?? null,
    pr_url: record?.pr ? `https://github.com/${RELEASES_REPO}/pull/${record.pr}` : null,
    summary: record?.summary || '',
    points: record?.points ?? [],
    published_at: typeof row.published_at === 'string' ? row.published_at : null,
    url,
  };
}

/**
 * Releases after `after` up to and including `through` (tags), newest first.
 * `after` null lists everything up to `through`. `more` counts the matches past
 * `limit`; `older_unlisted` says the page ended before reaching `after`, so
 * GitHub holds releases this list could not show.
 */
export function selectReleases(rows, { after = null, through, limit = RELEASE_NOTES_MAX_LISTED } = {}) {
  const top = tagNumber(through);
  const floor = tagNumber(after);
  const entries = (Array.isArray(rows) ? rows : []).map(releaseEntry).filter(Boolean);
  const matching = entries
    .filter((e) => top != null && e.number <= top && (floor == null || e.number > floor))
    .sort((a, b) => b.number - a.number);
  const oldest = entries.reduce((min, e) => Math.min(min, e.number), Infinity);
  const pageFull = Array.isArray(rows) && rows.length >= RELEASES_PER_PAGE;
  return {
    releases: matching.slice(0, limit),
    more: Math.max(0, matching.length - limit),
    older_unlisted: floor != null && pageFull && oldest > floor + 1,
  };
}

/**
 * Which releases the What's new card covers on this launch, or null for none.
 * `seen`: the release whose notes the operator last closed (null: never, e.g.
 * the first launch with What's new) -- then only the installed release is shown.
 */
export function whatsNewRange({ installed, seen }) {
  const now = tagNumber(installed);
  if (now == null) return null;
  const before = tagNumber(seen);
  if (before == null) return { after: `v${now - 1}`, through: installed, since: null };
  if (before >= now) return null;
  return { after: seen, through: installed, since: seen };
}

/** Plain text for a native dialog: newest first, cut to fit. */
export function notesText(releases, { maxChars = NOTES_TEXT_MAX_CHARS } = {}) {
  const parts = [];
  for (const e of releases ?? []) {
    const lines = [`${e.tag} -- ${e.title || 'no release notes recorded'}`];
    if (e.summary) lines.push(e.summary);
    for (const point of e.points ?? []) lines.push(`  - ${point}`);
    parts.push(lines.join('\n'));
  }
  const all = parts.join('\n\n');
  return all.length > maxChars ? `${all.slice(0, maxChars - 1)}…` : all;
}
