"""Per-PR ledger fragments: append a new file, never prepend to a shared one.

`CHANGELOG.md`, `PROBLEM_LOG.md` and `knowledge/task-log/INDEX.md` are written
by nearly every PR, and all three are **prepended** at line 1. With one author
that is tidy bookkeeping; with N agents it is N-squared conflict pairs on files
that carry no engineering value in the diff (#344, "the structural problem").

Two new files with distinct names cannot conflict. So a PR drops a fragment:

    .changes/unreleased/<utc-timestamp>-<slug>.md      -> CHANGELOG.md
    knowledge/problems/<utc-timestamp>-<slug>.md       -> PROBLEM_LOG.md

and a master-only job collates them into the ledger and deletes them, so only
one writer ever touches the ledger. This is the changesets / towncrier
"news fragment" pattern (#344 WS2, design principle 3).

A fragment is Markdown with a small front-matter block:

    ---
    kind: fix
    scope: capture
    pr: 371
    title: Stop deadlock on recorder stop
    ---
    - **What:** ...

Existing `CHANGELOG.md` / `PROBLEM_LOG.md` history is left untouched; only new
entries go to fragments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CHANGES_DIR = REPO_ROOT / ".changes" / "unreleased"
PROBLEMS_DIR = REPO_ROOT / "knowledge" / "problems"

CHANGELOG = REPO_ROOT / "CHANGELOG.md"
PROBLEM_LOG = REPO_ROOT / "PROBLEM_LOG.md"

# Both ledgers carry this marker; new entries are inserted immediately below it.
ENTRIES_MARKER = "<!-- ENTRIES_START -->"

KINDS = ("feat", "fix", "chore", "docs", "perf", "test", "refactor")

FRONT_MATTER = re.compile(r"\A---\n(?P<body>.*?)\n---\n(?P<rest>.*)\Z", re.S)

# A slug becomes part of a filename, so keep it to characters that are safe on
# every platform and unambiguous in a git path.
SLUG_OK = re.compile(r"\A[a-z0-9][a-z0-9-]{1,60}\Z")


@dataclass(frozen=True)
class Fragment:
    path: Path
    kind: str
    scope: str
    pr: str
    title: str
    body: str

    @property
    def stamp(self) -> str:
        """The leading timestamp of the filename, used only for ordering."""
        return self.path.name.split("-", 1)[0] if "-" in self.path.name else self.path.name


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60].strip("-")


def fragment_name(stamp: str, slug: str) -> str:
    return f"{stamp}-{slug}.md"


def render_fragment(*, kind: str, scope: str, pr: str, title: str, body: str) -> str:
    return (
        "---\n"
        f"kind: {kind}\n"
        f"scope: {scope}\n"
        f"pr: {pr}\n"
        f"title: {title}\n"
        "---\n"
        f"{body.rstrip()}\n"
    )


def parse_fragment(path: Path, text: str) -> Fragment:
    """Read one fragment. Raises ValueError with the path on malformed input.

    Strict on purpose: a fragment that silently parses wrong would drop a
    changelog entry, and the entry is the only record that the change happened.
    """
    match = FRONT_MATTER.match(text)
    if not match:
        raise ValueError(f"{path.name}: missing '---' front matter")
    fields: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"{path.name}: front-matter line is not 'key: value': {line!r}")
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()

    missing = [k for k in ("kind", "scope", "title") if not fields.get(k)]
    if missing:
        raise ValueError(f"{path.name}: front matter missing {', '.join(missing)}")
    if fields["kind"] not in KINDS:
        raise ValueError(
            f"{path.name}: kind {fields['kind']!r} is not one of {', '.join(KINDS)}"
        )
    body = match.group("rest").strip()
    if not body:
        raise ValueError(f"{path.name}: fragment has front matter but no body")
    return Fragment(
        path=path,
        kind=fields["kind"],
        scope=fields["scope"],
        pr=fields.get("pr", ""),
        title=fields["title"],
        body=body,
    )


def load_fragments(directory: Path) -> list[Fragment]:
    """Every fragment in a directory, oldest first.

    Filename order is timestamp order, which is what the ledger wants: within
    one collation run, entries read in the order the work happened.
    """
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.md")):
        if path.name.startswith("."):
            continue
        out.append(parse_fragment(path, path.read_text(encoding="utf-8")))
    return out


def render_entry(fragment: Fragment, *, date: str) -> str:
    """One ledger entry, in the shape the existing files already use."""
    pr = f" ([#{fragment.pr}](https://github.com/aaltaay/Nova/pull/{fragment.pr}))" if fragment.pr else ""
    return (
        f"## {date} — {fragment.title}{pr}\n"
        f"\n"
        f"{fragment.body}\n"
    )


def splice_entries(ledger_text: str, entries: list[str]) -> str:
    """Insert entries directly below the marker, newest first.

    Anchored on the real marker LINE, not on prose that happens to mention it
    -- that mistake is what corrupted CHANGELOG.md in #312, burying entries
    inside the how-to block.
    """
    if not entries:
        return ledger_text
    lines = ledger_text.splitlines(keepends=True)
    index = next(
        (i for i, line in enumerate(lines) if line.strip() == ENTRIES_MARKER),
        None,
    )
    if index is None:
        raise ValueError(f"ledger has no {ENTRIES_MARKER} line")
    block = "\n" + "\n".join(entry.rstrip() + "\n" for entry in entries)
    return "".join(lines[: index + 1]) + block + "".join(lines[index + 1 :])


def collate(
    directory: Path, ledger: Path, *, date: str, prune: bool = True
) -> tuple[int, list[Path]]:
    """Fold every fragment into the ledger and remove the fragment files.

    Returns (entries written, fragment paths consumed). Writing nothing when
    there are no fragments is the normal quiet case, not an error.
    """
    fragments = load_fragments(directory)
    if not fragments:
        return 0, []
    entries = [render_entry(f, date=date) for f in reversed(fragments)]
    ledger.write_text(splice_entries(ledger.read_text(encoding="utf-8"), entries), encoding="utf-8")
    consumed = [f.path for f in fragments]
    if prune:
        for path in consumed:
            path.unlink()
    return len(entries), consumed
