# Contributing to Verascope

Thanks for contributing — including as part of GSSOC. This doc is the fastest path from "cloned
the repo" to "opened a PR."

## Setup

Follow the **Setup** section in [README.md](README.md) first (Postgres via Docker, backend venv +
`alembic upgrade head`, frontend `npm install`). Come back here once you can log in at
`http://localhost:5173` and both `pytest` (backend) and `npm run build` (frontend) pass locally —
that's the same baseline CI checks on every PR.

You do **not** need an Anthropic/OpenAI/Ollama key to work on most of the codebase: ingestion,
parsing, the dependency graph, the security scanner, and the whole frontend outside of Chat/
Debugging work with no LLM configured. Only touch `services/llm/` or the agent prompts if the
change actually needs an LLM to verify.

## Before you start

- **Check open issues** for something labeled `good first issue` or `help wanted`, or open one
  describing what you want to work on before writing code — avoids duplicate effort on a project
  this size.
- **Read the file you're changing's neighbors first.** This codebase has strong existing
  conventions (see below); matching them matters more than personal style preference.
- For anything nontrivial, a short comment on the issue with your intended approach before you
  start saves a rewrite later.

## Conventions this codebase follows

- **Evidence over invention.** This is the one rule the whole project is built around (see the
  README's explanation of the name). Agents must cite real files/lines and say
  "insufficient evidence" rather than guess. If you touch an agent, keep that property.
- **SQLAlchemy 2.0 `Mapped`/`mapped_column` style**, not the legacy `Column()` style — see any
  file in `backend/app/models/` for the pattern.
- **Every DB failure path calls `db.rollback()` before `db.commit()`.** A commit on a poisoned
  transaction re-raises and silently leaves rows stuck (this was a real, fixed bug — see the
  README's "Verified during development" section, Pass 2, bug #4). New exception handlers that
  touch the DB must follow this pattern.
- **New background-job status values must be reachable from `reconcile_stuck_state()`**
  (`backend/app/core/reconcile.py`). If you add a new non-terminal `RepositoryStatus` or a new
  `StepStatus` that a job can get stuck in mid-transition, add it to that function's tracked
  statuses — otherwise a crashed job in that new status will sit stuck forever with no recovery,
  the exact failure mode this function exists to close.
- **Docstrings/comments explain *why*, not *what*.** Don't add a comment describing what the next
  line obviously does; do add one if there's a non-obvious constraint, a past bug it's guarding
  against, or a tradeoff a reader would otherwise question.
- **No placeholder/elided code**, ever — including in code the Fix Agent generates (there's an
  actual guard against this in `backend/app/agents/fix_tools.py`; don't weaken it) and including
  in your own PRs. Write complete, runnable code or don't include it.

## Tests

```bash
cd backend && pytest -q
cd frontend && npm run build   # typecheck (tsc -b) + build
```

Both must pass before you open a PR — CI runs the same two checks (plus an `alembic upgrade head`
against a fresh Postgres) on every push and PR via `.github/workflows/ci.yml`.

- Backend tests live in `backend/tests/` and currently favor small, dependency-free unit tests
  (fake sessions/objects rather than a live DB — see `tests/test_lifecycle.py` or
  `tests/test_reconcile.py` for the pattern) over integration tests against a real database. Follow
  that pattern unless your change genuinely can't be tested that way.
- If you fix a bug, add a regression test that would have caught it. Several existing tests exist
  specifically because of a real bug found during development (see the README's "Verified during
  development" section) — that's the standard to match.

## Pull requests

- Keep PRs scoped to one change. A bug fix doesn't need an unrelated refactor riding along.
- Fill in the PR template (it's short) — it asks what changed, why, and how you verified it.
- Reference the issue you're closing (`Closes #123`) if there is one.
- Expect review comments — this is a learning project for many GSSOC contributors as much as it's
  a working app; review feedback here is meant to be specific and actionable, not gatekeeping.

## Reporting bugs / requesting features

Use the issue templates under `.github/ISSUE_TEMPLATE/`. For a bug report, the single most useful
thing you can include is exact repro steps (which repository/URL, which page, what you clicked) —
this project's own testing process (see the README) repeatedly found real bugs that only showed up
under specific real-world conditions, not synthetic ones.

## Questions

Open a GitHub issue with the `question` label rather than a PR — cheaper for everyone if the
answer changes what you'd build.
