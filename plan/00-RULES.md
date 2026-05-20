# 00 — Rules (Non-Negotiable)

These rules are absolute. Every Claude Code session must respect them.

## Session protocol

### At session start (always)
1. Read `00-RULES.md` (this file)
2. Read `PROGRESS.md` — find the current open task and the "Up Next" queue
3. Read `KNOWLEDGE.md` — load current project state, decisions, and gotchas
4. Read `05-CODING-STANDARDS.md` — refresh conventions
5. Read the specific plan file relevant to the task (e.g., `06-AGENT-HARNESS.md` if working on extraction)

### During session
- Make small, verifiable commits. One logical change per commit.
- Use Conventional Commits format: `feat(scope): description`, `fix(scope): description`, `chore(scope): description`, `refactor(scope): description`, `docs(scope): description`, `test(scope): description`.
- When a decision needs to be made that wasn't in the docs, **pause and ask** rather than guessing. Don't invent design choices.
- Run linters and formatters before committing.
- Never leave broken code in `main`. Use feature branches if a task is multi-commit.

### At session end (always)
1. Update `PROGRESS.md`:
   - Mark completed tasks with `[x]` and a timestamp
   - Move next task to "Current"
   - Add any new blockers under "Blockers"
2. If a phase or major milestone completed, update `KNOWLEDGE.md`:
   - Add new architecture decisions
   - Add new gotchas discovered
   - Update schema state if DB changed
   - Update API endpoint list if endpoints added
3. Commit the doc updates separately from code: `docs(progress): close <task-id>`.

## Coding rules

- **Type everything.** TypeScript strict mode on. Python type hints required on every function signature.
- **No silent failures.** Every error path either logs with context or re-raises. No bare `except:` or `try/catch` that swallows errors.
- **Reusable chunks.** Functions > 50 lines must be split. Files > 400 lines must be split into logical modules.
- **No magic strings.** Constants live in `constants.py` / `constants.ts`. Env vars accessed only via a single typed config module.
- **No direct LLM calls in route handlers.** All LLM calls go through the agent harness module. Routes orchestrate, agents reason.
- **Idempotent jobs.** Every worker job must be safe to retry. Use document state machine; never assume "first time."
- **All money/sensitive numbers as `Decimal`, never `float`.** Even outside Phase 1's scope this is a discipline to bake in early.

## File and folder rules

- Never put business logic in API route handlers. Routes are thin: parse → call service → return.
- Services live in `services/`. Pure logic, no framework imports.
- Repositories live in `repositories/`. All DB access. No business logic.
- Agents live in `agents/`. One file per agent. Prompts in `agents/prompts/`.
- Utilities live in `utils/`. Only put things here if used in ≥ 2 places.

See `05-CODING-STANDARDS.md` for full structure.

## Security rules

- Never log raw document content. Log metadata only (file_hash, doc_id, user_id).
- Row-Level Security (RLS) is enabled on every Supabase table. Test RLS policies before assuming.
- API keys live only in env vars. Never commit `.env`. `.env.example` is the template.
- File uploads validated by MIME type AND magic bytes. Never trust the extension alone.
- All user-supplied strings escaped before any SQL (we use parameterized queries — no raw SQL with f-strings).

## When stuck

If a task is blocked or ambiguous:
1. Add a `BLOCKER` entry to `PROGRESS.md` with the question
2. Skip to the next non-dependent task if one exists
3. Don't guess — surface the question to the human

## Forbidden actions

- ❌ Don't modify `KNOWLEDGE.md` to "fix" a discrepancy with code. Fix the code or update the doc with reasoning.
- ❌ Don't add new dependencies without recording them in `KNOWLEDGE.md` under "Dependencies."
- ❌ Don't deploy without running all tests locally first.
- ❌ Don't disable RLS even temporarily.
- ❌ Don't merge feature branches without confirming PROGRESS.md is up to date.
