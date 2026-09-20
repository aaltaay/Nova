"""Conservative CI path selection; only CLI output files have write side effects."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import subprocess

LOG = logging.getLogger(__name__)
FIELDS = ("backend", "frontend", "e2e", "desktop", "source", "dependencies")
TRADING_FRONTEND = (
    "frontend/src/ibkr/", "frontend/src/bot/", "frontend/src/strategy/",
    "frontend/src/hotkeys/", "frontend/src/orders_today/", "frontend/src/closed_orders/",
    "frontend/src/execution_latency/", "frontend/src/sim/", "frontend/src/api/",
    "frontend/src/constantGroups/", "frontend/src/hooks/", "frontend/src/types/",
    "frontend/src/settings/", "frontend/src/hod_momo/", "frontend/src/lib/",
)
DEPENDENCY_NAMES = {
    "package.json", "package-lock.json", "requirements.txt", "requirements-dev.txt",
    "pyproject.toml", "poetry.lock", "uv.lock", "Pipfile", "Pipfile.lock",
}
SHA_PATTERN = re.compile(r"[0-9a-fA-F]{40}")


def full_scope() -> dict[str, bool]:
    return dict.fromkeys(FIELDS, True)


def classify(paths: list[str]) -> dict[str, bool]:
    """Union all changed paths; an empty/unknown change is deliberately full CI."""
    if not paths:
        return full_scope()
    scope = dict.fromkeys(FIELDS, False)
    for raw in paths:
        path = raw.replace("\\", "/")
        name = path.rsplit("/", 1)[-1]
        if path.startswith(("backend/", "frontend/")):
            if name in DEPENDENCY_NAMES:
                return full_scope()
            if path.startswith("backend/"):
                for field in ("backend", "e2e", "desktop", "source"):
                    scope[field] = True
            elif path.startswith(("frontend/src/", "frontend/public/", "frontend/e2e/")):
                for field in ("frontend", "e2e", "desktop", "source"):
                    scope[field] = True
                if path.startswith(TRADING_FRONTEND):
                    scope["backend"] = True
            else:
                return full_scope()  # shell, scripts, bundler and shared config
        elif path.startswith("site/"):
            # Static marketing site is not bundled into Nova Desktop.
            scope["dependencies"] |= name in DEPENDENCY_NAMES
            scope["source"] |= Path(name).suffix in {".js", ".ts", ".html"}
        elif path.endswith(".md") and (
            "/" not in path or path.startswith(("docs/", "knowledge/"))
        ):
            continue
        elif path.startswith(".changes/"):
            continue
        else:
            return full_scope()
    return scope


def changed_paths(event_name: str, event: dict, repo: Path) -> list[str] | None:
    """Read the full git diff without API file limits; no renames hides no source."""
    if event_name == "pull_request":
        pr = event["pull_request"]
        base, head = pr["base"]["sha"], pr["head"]["sha"]
        separator = "..."
    elif event_name == "push":
        base, head = event["before"], event["after"]
        separator = ".."
    else:
        return None
    if not all(isinstance(sha, str) and SHA_PATTERN.fullmatch(sha) for sha in (base, head)):
        raise ValueError("diff endpoints must be full commit SHAs")
    output = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", f"{base}{separator}{head}", "--"],
        cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    return [path.decode("utf-8", errors="surrogateescape") for path in output.split(b"\0") if path]


def select_scope(event_name: str, event: dict, repo: Path) -> dict[str, bool]:
    try:
        paths = changed_paths(event_name, event, repo)
    except (KeyError, TypeError, ValueError, OSError, subprocess.CalledProcessError):
        LOG.warning("CI diff unavailable; selecting all checks", exc_info=True)
        return full_scope()
    return full_scope() if paths is None else classify(paths)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError):
        LOG.warning("CI event unavailable; selecting all checks", exc_info=True)
        event = {}
    scope = select_scope(os.environ.get("GITHUB_EVENT_NAME", ""), event, Path.cwd())
    print(json.dumps(scope, sort_keys=True))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as stream:
            for key, value in scope.items():
                stream.write(f"{key}={str(value).lower()}\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write("## Selected verification\n\n| Check | Needed |\n|---|---|\n")
            for key, value in scope.items():
                stream.write(f"| {key} | {'yes' if value else 'no (unaffected)'} |\n")


if __name__ == "__main__":
    main()
