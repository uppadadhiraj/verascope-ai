# Verascope

[![CI](https://github.com/uppadadhiraj/verascope-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/uppadadhiraj/verascope-ai/actions/workflows/ci.yml)

AI Repository Intelligence & Autonomous Debugging Platform.

The name: *vera* (truth, Latin) + *-scope* (an instrument for examining) — an instrument for
finding the truth in a repository. That's the one design principle enforced everywhere in this
codebase: agents cite real files and real lines, distinguish observed fact from inference from
guess, and say "insufficient evidence" rather than invent an answer.

Verascope ingests a real repository (GitHub URL or ZIP), builds a structured, AI-readable
representation of it (files, symbols, dependency graph, vector embeddings, a fact/inference-tagged
summary), and gives specialized agents controlled tools to answer questions, investigate bugs,
propose fixes, run tests in an isolated Docker sandbox, and — only after explicit human approval
at each step — create a git branch, commit, and open a pull request.

See the flow in `docs/` (none yet) or just read `backend/app/agents/orchestrator.py`,
which is the actual end-to-end coordinator and the best map of the system.

## What's implemented

This is a working MVP of the full spec, verified against real repositories end-to-end during
development (see "Verified" below), not a scaffold of stubs. A few things are intentionally scoped
down from a "someday" version — see **Known limitations** below; each one is a deliberate,
documented tradeoff, not an oversight.

- **Auth**: register/login, bcrypt password hashing, JWT sessions, per-user repository ownership.
- **Ingestion**: GitHub clone or ZIP upload (path-traversal safe) → recursive scanner with
  configurable ignore rules → language detection → parsing → dependency graph → chunking →
  embeddings → repository summary. Every phase updates `Repository.status` for progress polling.
- **Parsing**: real AST-based parsing for Python (stdlib `ast`); regex + brace-matching
  extraction (documented as such, not claimed to be a full AST) for JavaScript/TypeScript,
  Java, C/C++. A parse failure is recorded per-file and never aborts the rest of ingestion.
- **Dependency graph**: import-level `IMPORTS` edges, resolved to actual repository files where
  possible (Python absolute/relative imports, JS/TS relative imports, Java FQN, C/C++ includes) —
  and actually rendered, not just data: an interactive force-directed graph page (pan/zoom/drag,
  click a node to inspect it, right-click to jump straight to that file in Explorer).
- **Vector search**: ChromaDB (embedded, no server) behind a `VectorStore` interface; local
  sentence-transformers embeddings by default (no API key required), OpenAI embeddings optional.
  Every call is timeout-protected (see "Verified" below for why that matters).
- **Repository summary**: rule-based facts (languages, frameworks, entry points, API routes,
  database, auth mechanism, test framework) plus an optional LLM synthesis pass for a natural-
  language purpose paragraph and inferences — explicitly separated from facts, and the summary
  degrades gracefully (documented "uncertain" note) if no LLM key is configured.
- **Agents**: Orchestrator, Planner, Repository Agent (chat/Q&A), Debugger Agent, Fix Agent,
  Test Agent, Security Agent (rule-based static analysis, no LLM dependency), Code Review Agent,
  Validation Agent. All LLM-backed agents share one tool-calling loop
  (`app/agents/runner.py`) with full observability (`AgentRun`/`ToolCall` rows).
- **Sandbox**: real Docker execution (`docker` SDK) with CPU/memory limits, network disabled by
  default, a command allowlist, timeouts, and guaranteed container cleanup — verified directly
  (allowlist rejection and network isolation both confirmed working, see `tests/`).
- **Autonomous fix loop**: bounded at `SANDBOX_MAX_ITERATIONS` (default 5), logs every iteration,
  always terminates, and now (after a live bug found and fixed — see below) rejects a common LLM
  failure mode where a "complete file rewrite" is actually a placeholder comment.
- **Human approval**: three explicit gates (CODE_CHANGE, GIT_OPERATION, PR_CREATION) — nothing
  downstream of a PENDING approval executes.
- **Git/PR**: branch/commit against the real repository clone (never the default branch directly),
  scoped correctly to the current fix attempt (see bug #2 below), optional GitHub PR creation via
  the API, both gated behind their approval.
- **Frontend**: React + TypeScript + Tailwind. Login/register, dashboard, repository
  overview with live ingestion progress, file explorer with syntax highlighting and semantic
  search, a dependency graph visualization, chat with citations, a debugging workflow page
  (plan → root cause → approval → diff → tests → approval → branch → approval → PR), a security
  findings page that distinguishes "never scanned" from "scanned, found nothing", and agent run
  history with per-tool-call detail.

## Verified during development (not just "should work")

Three separate testing passes, each against real data, each finding and fixing real bugs rather
than stopping once things looked plausible.

### Pass 1 — ingestion, chat, and the Ollama integration

- Full ingestion pipeline run against a real, non-trivial repository
  (`tiangolo/full-stack-fastapi-template`, 223 files): correctly detected FastAPI/Next.js/React,
  PostgreSQL, JWT auth, pytest, and extracted 23 real API routes with correct file/method/path.
- Semantic search returned the actual password-hashing functions, correctly ranked, for the
  query "password hashing". AST symbol extraction returned exact, correct line ranges and
  signatures.
- The security scanner's `.exec()`-vs-`eval()` false positive (SQLModel's `session.exec()` was
  initially flagged as unsafe `eval`/`exec` usage) was caught by this same test run, fixed, and
  locked in with a regression test.
- **LLM provider actually exercised end-to-end against local Ollama** (`llama3.1:8b`, no cloud
  key), not just implemented against the interface — Repository Chat gave correct, grounded,
  cited answers via real tool-calling; the Debugger Agent investigated with real tool calls and,
  when evidence was genuinely weak, correctly reported `evidence_status: INSUFFICIENT` rather
  than fabricating a root cause. This pass found and fixed four real bugs (truncated tool results
  silently breaking citations *and* risking dropped Fix Agent changes, missing citation sources,
  an unhelpful bare `KeyError` on a misnamed tool argument, and a self-contradictory
  `root_cause`/`evidence_status` pair) — three of which are provider-agnostic and would have
  eventually surfaced with Anthropic/OpenAI too, just less often.
- Known, documented model-capability caveat: with `llama3.1:8b` specifically, multi-hop debugging
  investigations sometimes surface weak evidence and correctly self-report `INSUFFICIENT` rather
  than finding the real root cause — chat/Q&A (simpler) was reliably accurate throughout. A
  larger local model or a frontier API model closes this gap; it's a model-quality tradeoff, not
  an infrastructure bug.

### Pass 2 — the full critical path, driven end-to-end for the first time

Pass 1 stopped at the Debugger Agent's investigation. This pass actually drove
**Debug → approve → Fix Agent → Test Agent → autonomous retry loop → Review Agent → Validation
Agent → approve → git branch/commit → PR-creation error path** end-to-end for the first time,
using a small purpose-built repo with a real, plantable bug — and separately stress-tested
ingestion against `pallets/flask`, `expressjs/express`, and `spring-projects/spring-petclinic`
concurrently, plus auth isolation, malformed input, and a ZIP path-traversal attack. Found and
fixed eight more real, mostly provider-agnostic bugs:

1. **Fix Agent could write a broken file and nothing caught it.** `modify_file` replaced an
   entire file's content with a placeholder comment (`# ... rest of the function remains the
   same ...`) instead of complete code — a well-known failure mode across LLM providers, not
   specific to local models. `create_file`/`modify_file` now reject content matching common
   elision idioms with a clear message, verified against the exact failure and regression-tested.
2. **Critical: a task's git commit could include stale/broken files from earlier failed
   autonomous-loop iterations.** The Test Agent, Validation Agent, and git branch-creation
   endpoint all queried `CodeChange` rows by `task_id` alone — across a task's full history,
   not scoped to the current fix attempt's `workspace_id`. In a live run this surfaced as 8
   `CodeChange` rows across 4 abandoned workspaces all being swept into a single git commit.
   Fixed by scoping all three to the current/latest `workspace_id` and de-duplicating by file
   path before committing.
3. **Critical: rescanning any repository failed outright.** The ingestion pipeline deleted old
   vector-store entries before re-embedding but never deleted old `RepositoryFile` /
   `RepositorySymbol` / `RepositoryDependency` rows before re-inserting — the very first rescan
   of any repository hit a `UniqueViolation` on `(repository_id, path)`. First-time ingestion
   always looked fine because there was nothing yet to conflict with. Fixed by clearing a
   repository's old rows (cascade-deletes symbols/dependencies) before every (re)scan.
4. **A mid-transaction DB error could leave a repository silently stuck forever.** When the bug
   above fired, the exception handler tried to `commit()` on an already-poisoned SQLAlchemy
   session without rolling back first, which raised again and prevented `status=FAILED` from
   ever being recorded — the repository sat at `SCANNING` indefinitely with a stale error
   message and no way to tell anything was wrong. Fixed by rolling back before every
   failure-path commit, backend-wide.
5. **ZIP-uploaded repositories' first git operation could fail outright on some machines.**
   `git.Repo.init()` used the host machine's `init.defaultBranch` git config (e.g. `master`)
   while `Repository.default_branch` always defaults to `main` in the DB — a mismatch that
   depends entirely on the developer's local git config. Fixed by explicitly naming the initial
   branch to match what the DB expects, independent of host configuration.
6. **JS/TS symbol extraction missed a very common pattern.** `obj.prop = function name() {}` /
   `A.prototype.m = function () {}` — the way most non-class, prototypal-style JS defines
   methods (this is literally how Express's own `lib/*.js` is written) — wasn't recognized at
   all. A real 632-line file (`express/lib/application.js`) yielded only 2 extracted symbols
   instead of 18. Fixed and regression-tested.
7. **On Windows, deleting a repo directory before re-cloning could fail with "Access is denied"**
   on git pack files (a known GitPython-on-Windows file-handle/read-only-attribute interaction;
   Linux, this project's Docker target, is unaffected). Fixed with a retry-with-backoff +
   read-only-clear helper, the same workaround pip/tox/conda use for the same OS behavior.
8. **ChromaDB calls had no timeout.** A `store.upsert()`/`search()` call hanging (observed live)
   left a repository stuck at `status=EMBEDDING` forever, or would have hung a live chat/search
   HTTP request indefinitely, with zero feedback. Every `ChromaVectorStore` call is now wrapped
   with a 60s timeout that raises a clear `VectorStoreTimeoutError` instead.

Also confirmed working correctly during this pass: cross-user repository access returns 404 (not
leaking existence), unauthenticated/malformed-token requests are rejected with 401, duplicate
registration and weak passwords are rejected with clear messages, invalid/non-existent GitHub
URLs fail with specific errors, and a ZIP containing a `../../../etc/...` path-traversal entry is
rejected before extraction with no filesystem escape.

### Pass 3 — real-user feedback on a real repository

A real user connected their own repository and used the product cold. That surfaced three UX
gaps that looked like bugs from the outside:

- **The Security page's "Run scan" button appeared to do nothing** on a genuinely clean
  13-file repository. Two real problems: the frontend checked for results exactly once, 3
  seconds after starting a scan (too short for anything but a tiny repo), and there was no way
  to distinguish "never scanned" from "scanned, found nothing" — both rendered as an identical
  empty state. Fixed: the frontend now polls until a new `Repository.last_security_scan_at`
  timestamp (a new, persisted field — deliberately not just client-side state, which would reset
  on every page reload) confirms the scan actually finished, and the empty state names which
  case you're in.
- **The Debugging page looked broken** ("I don't find any problems or recommendations") because
  it's reactive by design — it investigates a bug *you describe*, it doesn't proactively scan
  like Security does — but the empty state just said "No debugging tasks yet" with no
  explanation of that distinction. Rewritten to state the model explicitly.
- **Chat couldn't produce a requested architecture diagram**, because chat is text Q&A and
  architecturally cannot render one — but nothing pointed the user at the Dependency Graph page
  (built earlier in the session, evidence-grounded, not LLM-invented) that actually can. Added a
  visible link and updated the chat empty-state copy.

### Pass 4 — GSSOC readiness (contributor-facing, not user-facing)

A different kind of gap: everything above was verified as a *user* of the app. This pass checked
it as a *contributor* would — clone it, set it up, run the tests, open a PR — since that's the bar
that actually matters for GSSOC.

- **Crash recovery was a documented gap, not just implemented around.** A repository/task could
  get stuck in a non-terminal status forever if the backend process died or restarted mid-job (no
  heartbeat/recovery mechanism for the simple `BackgroundTasks` approach this MVP uses). Fixed with
  `backend/app/core/reconcile.py`, wired into a FastAPI `lifespan` startup hook: on every startup,
  anything left mid-job by whatever process existed before this one is — by definition, since this
  process hasn't dispatched anything yet — not actually still running, so it's safe to mark it
  `FAILED` with a clear, specific message instead of leaving it stuck silently. Verified three ways:
  a fake-session unit test (`tests/test_reconcile.py`), and a real run against a disposable Postgres
  with genuinely stuck rows inserted, confirmed recovered correctly end-to-end.
- **A bare `pytest` run from `backend/` silently exploded** for anyone who'd already ingested a
  repository through the app: pytest recursed into `data/repos/`/`data/workspaces/` (gitignored
  runtime storage — cloned repositories and Fix Agent workspaces) and tried to collect *those*
  projects' own `tests/test_*.py` files, which immediately failed on missing dependencies and
  aborted the entire run before a single real test executed. Every contributor who tries the app
  locally before running tests would hit this. Fixed with `backend/pytest.ini` (`testpaths = tests`).
- **No CI.** Added `.github/workflows/ci.yml`: backend job runs `alembic upgrade head` + an app
  import check + `pytest` against a real (ephemeral, containerized) Postgres; frontend job runs
  `npm run build` (typecheck + build). Both verified locally against a disposable Postgres
  container before being trusted, the same standard the rest of this README holds itself to.
- **No contributor-facing docs or templates.** Added `CONTRIBUTING.md` (setup recap, the
  codebase's actual conventions — e.g. the rollback-before-commit rule from Pass 2 bug #4, and the
  requirement that new stuck-able statuses get added to `reconcile_stuck_state()`), a bug report
  template, a feature request template, and a PR template under `.github/`.

## Known limitations (deliberate MVP scope, not gaps to hide)

- **Dependency graph is import-level, not a call graph.** `get_callers`/`get_callees` answer
  "what files import this file", not "what functions call this function". Good enough to trace
  execution paths for the MVP's debugging scenarios; a real call graph is a natural V2.
- **JS/TS/Java/C/C++ parsing is regex + brace-matching, not a true AST.** No tree-sitter/Node
  dependency was introduced for this MVP. It covers the common declaration shapes well; it is not
  claimed to be exhaustive.
- **Background jobs are FastAPI `BackgroundTasks`**, not Celery/Redis. Correct and simple for an
  MVP; a real queue is the natural V2 if you need retries or distribution across multiple worker
  processes. Crash recovery for the *current* process's in-flight jobs is handled (see Pass 4) —
  what a real queue would add on top is recovering jobs that were still running on a worker that's
  now gone, and retrying transient failures automatically.
- **Progress is polled, not pushed.** No websockets/SSE yet; the frontend polls status endpoints.
- **The security scanner doesn't distinguish string literals from real code.** Found live: a test
  fixture building an XSS payload string containing the text `eval(...)` was flagged as unsafe
  `eval` usage, because the regex has no tokenizer and can't tell a match inside a quoted string
  from an actual function call. Documented, not hidden — already-stated tradeoff of this
  scanner's regex-based approach (see `security_agent.py`'s own docstring).
- **Rescan re-runs the full pipeline** rather than diffing changed files incrementally.
- **The Fix Agent's tools operate on isolated workspace copies**, never the indexed clone or
  the user's real repository, until an explicitly approved git operation copies validated changes
  onto a new branch.

## Architecture

```
frontend/        React + TypeScript + Tailwind (Vite)
backend/
  app/
    core/        config, security (JWT/bcrypt), logging
    db/          SQLAlchemy base + session
    models/      15 tables: users, repositories, files, symbols, dependencies,
                 conversations, messages, tasks, task_steps, agent_runs, tool_calls,
                 findings, code_changes, test_runs, approvals, pull_requests
    schemas/     Pydantic API schemas
    services/
      ingestion/ scanner, language detection, parsers (python/js-ts/generic),
                 chunker, dependency_resolver, summary, pipeline
      vectorstore/ VectorStore interface + ChromaDB implementation + embedder
      llm/       LLMProvider interface + Anthropic/OpenAI/Ollama implementations
      git/       workspace management, git_ops (branch/commit/diff), github_client (PR)
      sandbox/   Docker sandbox executor, test framework detection + runner
    agents/      orchestrator, planner, repository_agent, debugger_agent, fix_agent,
                 test_agent, security_agent, review_agent, validation_agent,
                 runner (shared tool-calling loop), lifecycle (CodeChange state machine)
    api/routes/  auth, repositories, files, chat, tasks, changes, test_runs,
                 findings, approvals, agent_runs, git
    workers/     background job entry points (own DB session per job)
  alembic/       migrations
  tests/         pytest unit tests (parsers, scanner, security rules, dependency
                 resolution, CodeChange lifecycle state machine, fix-tool guards)
docker-compose.yml   Postgres (always) + backend/frontend (optional, `--profile full`)
```

### Why these infrastructure choices

- **ChromaDB runs embedded** (`PersistentClient`), not as a separate server — simpler to run,
  still swappable later via the `VectorStore` interface.
- **Postgres runs in Docker; backend/frontend run on the host** for dev, because the sandbox
  executor needs simple host-path volume mounts — running the backend itself in Docker would mean
  Docker-outside-of-Docker path translation for sandbox mounts, real complexity avoided here.
  Dockerfiles exist for a fully containerized run (`docker compose --profile full up --build`).

## Setup

### Prerequisites

- Python 3.11 or 3.12 (3.12 recommended for parity with the backend's own Docker image; a very
  new Python like 3.14 risks missing wheels for `chromadb`/`sentence-transformers`/`onnxruntime`)
- Node.js 20+ and npm
- Docker Desktop (for Postgres and the code-execution sandbox)
- An Anthropic, OpenAI, or local Ollama setup if you want chat/debugging to actually answer
  questions — ingestion, search, symbol browsing, and the security scanner all work with **no**
  LLM key configured. `.env.example` currently defaults to `LLM_PROVIDER=ollama` with
  `OLLAMA_MODEL=llama3.1:8b` (a model with real tool-calling support in Ollama -- plain `llama3`
  does not) since that's what this was actually developed and verified against; switch
  `LLM_PROVIDER`/the relevant `*_API_KEY` in `.env` to use Anthropic or OpenAI instead.

### 1. Start Postgres

```bash
docker compose up -d postgres
```

Runs on host port **5433** (not 5432) to avoid clashing with any other local Postgres install —
adjust `DATABASE_URL` in `.env` if you change this.

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

cp ../.env.example .env         # defaults to Ollama; set GITHUB_TOKEN if you want PR creation
alembic upgrade head

uvicorn app.main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`; interactive API docs at `http://localhost:8000/docs`.

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Frontend runs at `http://localhost:5173`.

### 4. Try it

1. Register an account at `http://localhost:5173/register`.
2. Add a repository (GitHub URL, e.g. a small FastAPI project — or upload a ZIP) and watch the
   ingestion progress bar.
3. Once ready, use **Explorer** (file tree + syntax highlighting + semantic search), the
   **Dependency Graph** (an actual rendered diagram — click a node to inspect it, right-click to
   open it in Explorer), and **Chat** (needs an LLM key in `backend/.env`).
4. Try **Debugging**: describe a bug, watch the Planner + Debugger Agent investigate, review the
   root cause and evidence, approve the proposed fix, watch the Fix Agent + Test Agent run in the
   Docker sandbox, review the diff, approve the git branch/commit, and (for GitHub-sourced repos)
   approve and open a PR.
5. Check **Security** for a no-LLM-required static scan (the empty state tells you whether it's
   never been run or genuinely came back clean), and **Agent History** for full tool-call-level
   observability of everything the agents did.

### Docker sandbox notes

The Test/Fix agents execute inside disposable containers (`python:3.12-slim` /
`node:20-slim` by default — pulled on first use). Network is disabled by default
(`SANDBOX_NETWORK_DISABLED=true`); if a project's test suite needs network access for setup,
that's a deliberate safety default to reconsider per-deployment, not a bug.

## Environment variables

See `.env.example` at the repo root (copied into `backend/.env` for local runs) for the full,
documented list: app/secret config, database, vector store, LLM provider selection
(`LLM_PROVIDER=anthropic|openai|ollama`), embedding provider, GitHub token, and sandbox limits.

## Running tests

```bash
cd backend
pytest tests/ -v
```

```bash
cd frontend
npm run build   # type-checks (tsc -b) then builds
```

CI (`.github/workflows/ci.yml`) runs these same two checks on every push/PR, plus
`alembic upgrade head` and an app-import check against a fresh Postgres — catching migration and
startup-time errors that a unit test run alone wouldn't.

## Contributing

Contributions welcome, including as part of GSSOC — see [CONTRIBUTING.md](CONTRIBUTING.md) for
setup, this codebase's conventions, and the PR process.
