# Developer Assessment: Full-Stack Engineering & Quality Assurance

## Overview

This assessment evaluates your engineering skills across the full development lifecycle:

- Code review, bug identification, and debugging
- Automated testing (Backend pytest & Frontend Playwright E2E) and manual test planning
- Technical specification & requirement analysis
- Clean Git workflow & Docker containerization
- Database optimization & query tuning

**Estimated Duration**: 1–2 days.

---

## Assessment Structure

The evaluation is organized into progressive tiers:

```
┌─────────────────────────────────────────────────────────────┐
│  Tier 1: Bug Hunting & Critical Fixes        (Mandatory)    │
├─────────────────────────────────────────────────────────────┤
│  Tier 2: Testing Strategy & Implementation   (Mandatory)    │
├─────────────────────────────────────────────────────────────┤
│  Tier 3: Advanced Engineering Skills         (Mandatory)    │
│    Task 3A: Technical Spec Writing (Todo Sharing)           │
│    Task 3B: Docker & Infrastructure Optimization            │
│    Task 3C: Database Indexing & Query Tuning                │
├─────────────────────────────────────────────────────────────┤
│  Tier 4: Optional Extension (Todo Tags & Bulk Actions)      │
└─────────────────────────────────────────────────────────────┘
```

---

## Tier 1: Bug Hunting & Fixes (Required - 30 pts)

The codebase has intentional issues across authentication, business logic, caching, and state management.

### Scope:

1. **Identify and report** the most impactful issues in your Pull Request description using this structure:
   - **Location**: file path and line number/function
   - **Severity**: Critical / High / Medium / Low
   - **Reason**: Why it is a problem (security flaw, data leak, regression)
   - **Fix Proposal**: Concise explanation or patch
2. **Implement fixes** for at least **5 meaningful issues** (including at least **2 backend** and **1 frontend**).
3. Focus on correctness, authorization, and data isolation rather than minor styling tweaks.

---

## Tier 2: Testing Strategy & Implementation (Required - 25 pts)

A quality engineer writes tests that verify critical business paths and guard against regressions.

### 2A. Backend Automated Tests (pytest)

Write tests in `backend/tests/` verifying at least **3 critical scenarios** from:

- Expired or tampered JWT access token rejection.
- Authorization boundary: User A cannot read, update, or delete User B's todos.
- Boolean toggle: Updating `completed` from `true` back to `false` persists correctly.
- Incomplete partial update: Updating title does not erase description.
- Cache invalidation: Creating, updating, or deleting a todo removes stale Redis cache.

Run backend tests:

```bash
cd backend
pytest tests/ -v
```

### 2B. Playwright End-to-End (E2E) Tests

Setup Playwright from scratch in the repository (e.g., in an `e2e/` folder or within `frontend/`) and implement at least **2 automated browser test scenarios**:

1. **Full User Journey**: Register/Login → Create a todo → Toggle completion → Verify item in UI → Logout.
2. **Cross-User Data Isolation**: User A creates a private todo; User B logs in on another session and confirms the item is NOT visible.

Provide clear commands in your PR to run the E2E suite headless or headed:

```bash
npx playwright test
```

### 2C. Manual Test Plan

Submit a structured markdown document (refer to [`templates/TEST_PLAN_TEMPLATE.md`](templates/TEST_PLAN_TEMPLATE.md) or embed in your PR):

- Test scenarios covering Authentication & Authorization.
- Preconditions, test steps, expected vs actual results.
- Severity and priority classifications.

---

## Tier 3: Advanced Engineering Skills (Required - 30 pts)

Candidates must complete **all three tasks** below (10 pts each):

---

### Task 3A: Technical Specification Writing (Todo Sharing) (10 pts)

Assume product stakeholders provided the following high-level feature request:

> _"Users should be able to share their todo list with other users with either read-only (viewer) or edit (editor) permissions, and owners can revoke access anytime."_

Your task is **not** to implement the code, but to produce a production-grade specification document `docs/TODO_SHARING_SPEC.md` (use [`templates/SPEC_TEMPLATE.md`](templates/SPEC_TEMPLATE.md) as a guide):

- **User stories & Acceptance criteria**: Detailed scenarios.
- **Data model**: Proposed tables, fields, types, foreign keys, unique constraints, and cascade delete behavior.
- **API design**: Endpoints, request schemas, status codes, and error payloads.
- **Authorization & Edge cases**: Self-sharing prevention, duplicate invites, concurrent updates, immediate cache invalidation upon revoking permission.
- **Out of Scope**: Explicit boundaries to keep the release lean.

---

### Task 3B: Docker & Infrastructure Optimization (10 pts)

Inspect the current container setup (`docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`).

Implement improvements addressing at least **3 of the following**:

- Add dependable **healthchecks** for PostgreSQL and Redis; configure backend `depends_on` with `condition: service_healthy` so it won't crash on cold boot.
- Create `.dockerignore` files for both backend and frontend to exclude `node_modules`, `venv`, `test.db`, and build caches.
- Optimize image sizes using multi-stage builds or slim base images.
- Provide a clean `docker-compose.prod.yml` or production-ready configuration separating dev reload from production execution.
- Security enhancement: Ensure Redis is secured and secrets are not leaked in image layers.

---

### Task 3C: Database Performance & Indexing Strategy (10 pts)

The project includes a seed script capable of creating large datasets:

```bash
docker compose exec -e SEED_USERS=10000 -e SEED_TODOS=1000000 backend python -m app.db.seed
```

Analyze database performance:

1. Run `EXPLAIN ANALYZE` on core queries (user-filtered todo queries, ordering by `created_at`, counting todos) before adding indexes.
2. Formulate and apply optimal indexes via an Alembic migration (e.g., composite index on `(user_id, completed, created_at)`).
3. Document a benchmark table in your PR showing query execution time **Before vs After** optimization.
4. Explain index tradeoffs: write latency impact, index storage overhead, and migration safety on large production tables.

---

## Tier 4: Optional Extension: Todo Tags, Filtering & Bulk Actions (Bonus +15 pts)

If you finish all mandatory tiers early and want to demonstrate broader full-stack implementation ability, implement the feature below.

### Database Schema

Create the following tables and relationships:

- **`tags`**
  - `id`: UUID primary key
  - `user_id`: UUID foreign key referencing `users(id)`, not null
  - `name`: VARCHAR(50), not null
  - `color`: VARCHAR(20), nullable
  - `created_at`: TIMESTAMPTZ, not null
  - `updated_at`: TIMESTAMPTZ, not null
- **`todo_tags`**
  - `todo_id`: UUID foreign key referencing `todos(id)`, not null
  - `tag_id`: UUID foreign key referencing `tags(id)`, not null
  - Primary key: `(todo_id, tag_id)`

Constraints and indexes:

- Case-insensitive unique tag names per user.
- Indexes on `tags(user_id)`, `todo_tags(tag_id)`, `todo_tags(todo_id)`, and `todos(user_id, completed, created_at)`.

### API Endpoints

- `GET /tags`: list all tags of the authenticated user.
- `POST /tags`: create a new tag.
- `PATCH /tags/{tag_id}`: rename/update a tag.
- `DELETE /tags/{tag_id}`: delete a tag and its todo-tag relations.
- `GET /todos?status=&tag_id=&keyword=&date_from=&date_to=&page=&page_size=`: list todos with filtering and pagination.
- `POST /todos/{todo_id}/tags`: attach a tag to a todo.
- `DELETE /todos/{todo_id}/tags/{tag_id}`: detach a tag from a todo.
- `PATCH /todos/bulk-status`: bulk update status.
  - Payload: `{ "todo_ids": ["uuid-1", "uuid-2"], "completed": true }`

### Backend Rules

- Users must only interact with their own tags and todos.
- Users can only attach their own tags to their own todos.
- Tag names must be unique per user, case-insensitively.
- Bulk updates must run in a database transaction.
- Todo pagination must order by `created_at DESC, id DESC`.
- Redis cache for todo lists must scope by user and query/filter parameters.
- Cache must be invalidated on create, update, delete, tag mapping, and bulk updates.

### Frontend Requirements

- Todo list filter bar with keyword, status, tag, date range, and clear filters.
- Todo item UI displaying attached tags.
- Tag management UI for list/create/rename/delete.
- Bulk actions for selecting multiple todos and marking them completed or active.
- Use `@tanstack/react-query` for data fetching and mutations.
- Query keys must include all filter parameters.
- Invalidate query cache correctly after mutations.
- Use `react-hook-form` and `zod` for validation matching the backend.
- Clear user-scoped cached data on logout.

### Suggested Tests

- Backend: create tag success, duplicate tag casing, cross-user access prevention, attaching another user's tag prevention, filtering by tag, bulk update ownership check, cache invalidation.
- Frontend: tag form validation, todo filter query key behavior, bulk action success/error handling, logout clearing cached data.

---

## Git Workflow & Submission Guidelines (15 pts)

A clean Git history reflects professional engineering discipline:

- **Repository Setup**: Fork this repo, work inside your fork on a branch named `assessment/<your-name>` or `feature/<topic>`.
- **Atomic Commits**: Group related changes logically. Do not lump all fixes into a single generic commit.
- **Conventional Commits**: Format commit messages conforming to [Conventional Commits](https://www.conventionalcommits.org/):
  ```
  fix(auth): enforce token expiration in verify_token
  feat(todos): check user ownership before updating todo
  test(e2e): add playwright cross-user isolation test
  docs(spec): add todo sharing technical specification
  ```
  _(A `.commitlintrc.json` configuration is pre-configured in this repository)._
- **Pull Request Submission**:
  - Open a PR in your fork targeting your default branch.
  - Detail all findings, test results, reproduction commands, and trade-offs directly in the PR description.
  - If AI coding assistants were used, disclose them and include any prompt logs or configurations.

---

## Local Setup & Quick Start

Follow the instructions in [GUIDE.md](GUIDE.md) to launch services with Docker or local virtual environments.
