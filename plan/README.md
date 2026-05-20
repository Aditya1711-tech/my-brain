# Project Brain — Phase 1 Plan

This folder is the source of truth for the Phase 1 build. Every Claude Code session **must** read these files before touching code.

## File index (read order)

| # | File | Purpose | When to read |
|---|------|---------|-------------|
| 0 | `00-RULES.md` | Non-negotiables for every session | Every session, start |
| 1 | `01-OVERVIEW.md` | What we're building, scope, demo target | Once, at start of project |
| 2 | `02-TECH-STACK.md` | Pinned stack + setup commands | Day 1; reference later |
| 3 | `03-ARCHITECTURE.md` | Services, data flow, API contracts | Once; reference during integration |
| 4 | `04-DATA-MODEL.md` | DB schema + migrations | When touching DB |
| 5 | `05-CODING-STANDARDS.md` | Folders, patterns, conventions | Every coding session |
| 6 | `06-AGENT-HARNESS.md` | 5-agent pipeline detail + prompts | When working on harness |
| 7 | `07-EXECUTION-PLAN.md` | Day-by-day sequential plan | When working sequentially |
| 8 | `08-PARALLEL-TRACKS.md` | Multi-session parallel execution | When running parallel sessions |
| L1 | `PROGRESS.md` | Living checklist — updated each task | Every session, start AND end |
| L2 | `KNOWLEDGE.md` | Living knowledge — updated each phase | Every session, start AND end of phase |

## Quick start for any Claude Code session

```
1. Read 00-RULES.md
2. Read PROGRESS.md (find current task)
3. Read KNOWLEDGE.md (load current project state)
4. Read 05-CODING-STANDARDS.md (refresh conventions)
5. Read the specific plan file relevant to current task
6. Execute task
7. Update PROGRESS.md (mark task done, set next)
8. If phase complete: update KNOWLEDGE.md
```

## Session boundaries

A "session" is one Claude Code invocation. Sessions are short-lived; the docs are persistent. Treat PROGRESS.md and KNOWLEDGE.md like a daily standup written for your future self.
