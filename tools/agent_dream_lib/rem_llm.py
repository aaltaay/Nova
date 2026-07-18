"""LLM-backed REM narrative with heuristic fallback."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _load_dotenv(repo_root: Path) -> None:
    env_path = repo_root / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_path)


def llm_rem_available(repo_root: Path) -> bool:
    _load_dotenv(repo_root)
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def build_rem_prompt(themes: list[dict[str, Any]], samples: list[str]) -> str:
    theme_line = ", ".join(f"{t.get('theme')}×{t.get('count')}" for t in themes[:10]) or "(none)"
    bullets = "\n".join(f"- {s}" for s in samples[:24]) or "- (no learnings)"
    return (
        "You are Nova's REM dream consolidator for a multi-agent coding fleet.\n"
        "Write a short Dream Diary (6-12 sentences) that names recurring themes, "
        "risks to watch, and what durable lessons should stay vs be pruned.\n"
        "Do not invent product facts. Do not suggest live trading or auto_live.\n"
        "Do not use bullet lists of commands — prose diary only.\n\n"
        f"Heuristic themes: {theme_line}\n\n"
        f"Recent learnings / pending facts:\n{bullets}\n"
    )


def run_llm_rem(
    themes: list[dict[str, Any]],
    samples: list[str],
    repo_root: Path,
    *,
    model: str = "gpt-4o-mini",
) -> tuple[str | None, str]:
    """Return (narrative, mode) where mode is llm|heuristic|skipped."""
    if not llm_rem_available(repo_root):
        return None, "heuristic"
    try:
        from openai import OpenAI
    except ImportError:
        return None, "heuristic"

    _load_dotenv(repo_root)
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    prompt = build_rem_prompt(themes, samples)
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0.4,
            max_tokens=500,
            messages=[
                {
                    "role": "system",
                    "content": "You write concise REM dream diaries for AI agent fleets.",
                },
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:  # noqa: BLE001 — dream must degrade gracefully
        # Fall back to heuristic REM; keep error out of the durable diary body.
        _ = exc
        return None, "heuristic"
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        return None, "heuristic"
    return text, "llm"
