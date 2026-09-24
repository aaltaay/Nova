"""Filing a GitHub issue from the desk: the operator's bug or feature, posted to the repo.

Operator ask, 2026-09-24: "when I do the update, I can also click and say 'File an issue'
... it goes directly to GitHub". The desk's form sends a kind (bug | feature), a title and the
details; ``compose`` builds the issue (desk context, secrets redacted) and ``gh_filer`` posts it
through the GitHub CLI already signed in on this PC -- Nova never reads the token. Without a
signed-in CLI the answer carries GitHub's new-issue link, prefilled, for the operator to submit.
The repository is public, so nothing here attaches an account id, a path or a key.
Nothing here places, stages or cancels an order. Schema: AGENTS.md §3.
"""
