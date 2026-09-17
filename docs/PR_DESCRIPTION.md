# Developer Assessment — Phi Long

All mandatory tiers are complete, and so is the optional Tier 4. 27 commits,
each scoped to one concern; every backend commit passes its own test suite.

| Tier | Deliverable | Where |
|---|---|---|
| 1 — Bug hunting | 28 defects found, 28 fixed (20 backend, 8 frontend) | §1, commits `c19d6e5`…`9795b6c` |
| 2A — pytest | 76 new tests, 85 total | `backend/tests/` |
| 2B — Playwright | 17 E2E specs, set up from scratch | `e2e/` |
| 2C — Manual test plan | 81 cases with results | [`docs/MANUAL_TEST_PLAN.md`](docs/MANUAL_TEST_PLAN.md) |
| 3A — Spec | Todo sharing specification | [`docs/TODO_SHARING_SPEC.md`](docs/TODO_SHARING_SPEC.md) |
| 3B — Docker | 5 of 5 suggested improvements | §4 |
| 3C — DB indexing | 182× on the list query, measured | [`docs/DB_PERFORMANCE.md`](docs/DB_PERFORMANCE.md) |
| 4 — Optional | Tags, filtering and bulk actions, full stack | §7 |

AI assistance is disclosed in [`docs/AI_USAGE.md`](docs/AI_USAGE.md) as the
README requires.

---

## 1. Tier 1 — Findings

Severity is impact if exploited or hit in production. Every **Critical** and
**High** item has a regression test that fails on `main` and passes here.

### 1.1 Critical

#### F-01 · Expired tokens never expire
- **Location**: `backend/app/core/security.py:56` (`verify_token`)
- **Reason**: `jwt.decode(..., options={"verify_exp": False})`. Every access
  token ever issued stayed valid forever. `ACCESS_TOKEN_EXPIRE_MINUTES` was
  decorative — a token leaked from a log or a browser was a permanent
  credential.
- **Fix**: Removed the override so expiry is always verified.
- **Test**: `test_auth_security.py::test_expired_access_token_is_rejected`

#### F-02 · A refresh token authenticates any request
- **Location**: `backend/app/api/deps.py:21` (`get_current_user`)
- **Reason**: The `type` claim was written but never read. The 7-day refresh
  token worked anywhere the 30-minute access token did, so the short access
  lifetime bought nothing.
- **Fix**: `verify_token(token, expected_type="access")`; `/auth/refresh`
  likewise requires a refresh-type token.
- **Tests**: `test_refresh_token_cannot_be_used_as_access_token`,
  `test_access_token_cannot_be_used_to_refresh`

#### F-03 · One user's todo list served to every other user
- **Location**: `backend/app/api/v1/todos.py:37`
- **Reason**: `cache_key = "todos:list"` — a single global key. Whoever
  listed first populated it and for the next five minutes **every other user
  received that cached body**. The SQL was correctly filtered by `user_id`
  the whole time, so the breach was invisible from the ORM layer. The worst
  bug in the codebase.
- **Fix**: Key is `todos:list:{user_id}:page={p}:size={s}`.
- **Tests**: `test_cache.py::test_cached_list_is_not_served_across_users`,
  `cross-user-isolation.spec.ts`

#### F-04, F-05, F-06 · IDOR on read, update and delete
- **Location**: `backend/app/api/v1/todos.py:95, 114, 145`
- **Reason**: All three handlers fetched by id alone and never compared the
  row against `current_user`. Any authenticated account could read, edit or
  delete **any** other account's todo by id.
- **Fix**: `get_todo_by_id(db, todo_id, user_id)` puts the owner in the
  `WHERE` clause, so no code path can reach another user's row. A miss
  returns `404`, not `403` — answering "exists, but not yours" still leaks
  which ids are real.
- **Tests**: `test_authorization.py` (3 tests), `cross-user-isolation.spec.ts`

#### F-07 · Logging out left the previous user's data in the browser
- **Location**: `frontend/src/features/auth/hooks/useAuth.ts:23`
- **Reason**: Logout removed the two localStorage tokens and left the
  react-query cache untouched. Its keys are per query *name*, not per user,
  so the next person to sign in on that browser was served the previous
  account's `["currentUser"]` and `["todos"]` entries from memory — another
  user's todos rendered with no request made. Shared or kiosk machines leak
  outright.
- **Fix**: Login and logout both clear the cached data; logout does it from
  `onSettled` so a failed logout call still cleans up.
- **Test**: `cross-user-isolation.spec.ts` ("logging out clears the cached
  list")

### 1.2 High

#### F-08 · A completed todo could never be reopened
- **Location**: `backend/app/api/v1/todos.py:123`
- **Reason**: `if todo_data.completed:` tests truthiness, so `completed=false`
  was silently discarded.
- **Fix**: Apply `model_dump(exclude_unset=True)` as-is; `false` is a value
  like any other.
- **Test**: `test_todo_updates.py::test_completed_can_be_set_back_to_false`

#### F-09 · Partial updates destroyed data
- **Location**: `backend/app/api/v1/todos.py:121`
- **Reason**: `model_dump()` without `exclude_unset` materialises every absent
  optional field as `None`, so editing a title blanked the description.
- **Fix**: As F-08. A field that is sent is written; one that is not is
  untouched; an explicit `null` still clears the column.
- **Tests**: `test_partial_update_preserves_untouched_fields`,
  `test_partial_update_preserves_completed_flag`,
  `test_description_can_be_cleared_explicitly`

#### F-10 · Nothing invalidated the cache
- **Location**: `backend/app/api/v1/todos.py` — create, update, delete
- **Reason**: `redis` was injected into update and delete and never used;
  create did not even inject it. A new or edited todo did not appear for up to
  5 minutes.
- **Fix**: Each write drops that user's cached pages via a SCAN-based
  `delete_pattern`, which leaves other users' entries alone.
- **Tests**: `test_cache.py` — create / update / delete / scoping (4 tests)

#### F-11 · Login was an account-enumeration oracle
- **Location**: `backend/app/api/v1/auth.py:54-66`
- **Reason**: `404 "User with this email not found"` for an unknown address
  vs `401 "Incorrect password"` for a wrong one. Anyone could enumerate which
  addresses have an account.
- **Fix**: Both return an identical `401 "Invalid email or password"`.
- **Test**: `test_login_does_not_reveal_whether_email_exists`

#### F-12 · Logout did nothing
- **Location**: `backend/app/api/v1/auth.py:102`
- **Reason**: Returned `"Successfully logged out"` and touched nothing. With
  F-01, a token stolen from a shared machine was valid forever.
- **Fix**: The presented token's `jti` is blacklisted in Redis with a TTL
  equal to the token's own remaining life, so the blacklist stays bounded.
- **Test**: `test_logout_revokes_the_access_token`

#### F-13 · `users.email` had no unique constraint
- **Location**: `backend/app/models/user.py:21`
- **Reason**: Two accounts could share an address. `get_user_by_email` uses
  `scalar_one_or_none()`, which raises `MultipleResultsFound` the moment that
  happens — a duplicate breaks login for **both** accounts. The handler's
  pre-check is not a guard: two concurrent registrations both pass it before
  either commits. No index either, so every login scanned the table.
- **Fix**: Unique index, in a migration that collapses any pre-existing
  duplicates first so the build cannot abort on live data.
- **Test**: `test_database_rejects_duplicate_emails`

#### F-14 · A failed login reloaded the page before the error could be read
- **Location**: `frontend/src/lib/api.ts:30`
- **Reason**: The 401 interceptor fired on *every* 401, including the one a
  failed login legitimately returns: it wiped storage and hard-navigated to
  `/login`, so the error toast never survived.
- **Fix**: 401s from the auth endpoints pass through to the caller.
- **Test**: `user-journey.spec.ts` ("a wrong password shows an error")

#### F-15 · Paging did nothing
- **Location**: `frontend/src/features/todos/api/todos.ts:37`
- **Reason**: `queryKey: ["todos"]` while the request varied by `page` and
  `size`, so page 2's response overwrote page 1 under the same key.
- **Fix**: `["todos", { page, size }]`, plus the matching per-page cache key
  on the server.
- **Test**: `test_cache.py::test_cache_key_distinguishes_pages`

#### F-16 · The client fetched the entire table
- **Location**: `frontend/src/features/todos/api/todos.ts:35`
- **Reason**: `size = 10000` by default, with no pagination UI.
- **Fix**: Page size 20 with real prev/next controls; the API caps `size` at
  100 so one request cannot pull the table.
- **Test**: `test_todo_updates.py::test_oversized_page_size_is_rejected`

#### F-17 · No index on `todos`
- **Location**: `backend/app/models/todo.py`
- **Reason**: Every list request sequential-scanned 1,000,000 rows to return
  20. See §5.
- **Fix**: `(user_id, created_at DESC, id DESC)`, built `CONCURRENTLY`.

### 1.3 Medium

| ID | Location | Reason | Fix |
|---|---|---|---|
| F-18 | `todos.py:49` | One `SELECT` on `users` per row, to attach an email already in hand — a pure N+1, 20 extra round trips per page | Use `current_user.email`; the rows are filtered on his id |
| F-19 | `todo_service.py:31` | No `ORDER BY` with `OFFSET`/`LIMIT`: Postgres may return a row on two pages or none | `ORDER BY created_at DESC, id DESC` — a total order, since `created_at` is not unique |
| F-20 | `auth.py:84` | `/refresh` checked the token type but never confirmed the account still exists, and left the token replayable for its whole life (which F-01 made unlimited) | User re-check and rotation — the presented token is revoked on use |
| F-21 | `main.py:31` | `allow_origins=["*"]` with `allow_credentials=True` — rejected by browsers, and trusts every origin | Explicit `CORS_ORIGINS`; a wildcard is refused by a validator |
| F-22 | `schemas/user.py:9` | No password bounds. bcrypt silently truncates past 72 bytes, leaving the tail of a long password unverified | 8–72 characters, enforced both ends |
| F-23 | `todos.ts:76` | `onMutate` returned a snapshot nothing restored, so a rejected update stayed on screen | `onError` rolls back every snapshotted page |
| F-24 | `TodoList.tsx:42` | `key={index}` — React reuses a deleted row's DOM node for its replacement, sliding checkbox state onto the wrong todo | `key={todo.id}` |
| F-25 | `frontend` | `/auth/refresh` existed but nothing ever called it, so every session died after 30 minutes | The interceptor refreshes once and replays the request; concurrent 401s share one in-flight refresh |

### 1.4 Low

| ID | Location | Reason | Fix |
|---|---|---|---|
| F-26 | `config.py:9` | `DB_ECHO = True` by default — every statement and its bound values to stdout: row data in the logs, plus throughput | Off by default |
| F-27 | `redis.py:19` | `close()` is deprecated in redis-py 5 | `aclose()` |
| F-28 | `schemas/auth.ts:5` | Form required 6 characters where the API requires 8 — a valid-looking form producing an unactionable 422 | Bounds mirrored from the backend |

Two further defects were introduced and fixed **within this branch** rather
than inherited; they are listed for completeness because the commits are in
the history: `baa45b5` (clearing the query cache from inside a mutation's own
`mutationFn` can drop that mutation's callbacks) and `37911bc` (an E2E race).

---

## 2. Tier 2A — Backend tests

```bash
cd backend && pytest tests/ -v
```

**85 passed** (9 pre-existing + 76 new). The four files below cover Tier 1;
`test_tags.py` and `test_todo_filters.py` cover Tier 4 (§7).

| File | Covers |
|---|---|
| `test_auth_security.py` | Token expiry, forged signatures, access/refresh separation, enumeration, logout revocation, refresh rotation, deleted accounts, password bounds, the unique-email constraint |
| `test_authorization.py` | Cross-user read / update / delete, list scoping, unauthenticated access |
| `test_todo_updates.py` | `completed=false` round-trip, partial updates, explicit null, ordering, page-size cap |
| `test_cache.py` | Per-user scoping, per-page keys, invalidation on create/update/delete, invalidation scoping |

**These tests were run against the pre-fix code: 22 of the 29 fail there.**
The 7 that pass cover behaviour that was already correct and are there as
guards.

`conftest.py` gained a `FakeRedis` that stores values for real. The previous
double was a `MagicMock` whose `get()` returned `None` unconditionally — which
means *no caching test written against it could ever fail*, since a stale or
cross-user read is exactly what it cannot reproduce.

## 3. Tier 2B — Playwright

Set up from scratch in `e2e/`.

```bash
docker compose up -d --build     # from the repo root
cd e2e && npm install
npx playwright install chromium  # first run only
npx playwright test              # headless
npx playwright test --headed     # headed
```

**17 passed**, and **34/34 across three `--repeat-each=2` runs** to rule out
flakiness. Seven specs cover Tier 1, ten cover Tier 4 (§7).

1. **Full journey** — register → create → toggle complete → survives reload →
   toggle back to active → logout → protected route bounces → log back in and
   the todo is still there.
2. **Cross-user isolation** — two separate browser contexts; A's private todo
   is invisible to B before and after a reload.
3. **The same at API level** — B gets `404` on read, update and delete of A's
   todo, and A's row is verified unchanged.
4. Logging out clears the cached list before the next account signs in.
5. A title-only edit keeps the description.
6. A wrong password shows its error instead of reloading.
7. An unauthenticated visitor is redirected to `/login`.

`toggleTodo()` waits for the `PUT` to return before continuing: the checkbox
flips optimistically, so asserting on the UI proves nothing about the server,
and reloading straight after the click aborts the in-flight request — which is
how the first run of this suite failed.

## 4. Tier 3B — Docker

All five suggested improvements, plus the build-arg bug.

| Item | Before | After |
|---|---|---|
| **Healthchecks** | `depends_on` only waits for container creation, so the backend raced Postgres and `alembic upgrade head` died on a cold boot | Postgres and Redis healthchecks; backend waits for `service_healthy`; frontend waits for the backend's. **Verified from empty volumes: 0 restarts** |
| **`.dockerignore`** | None, so `COPY . .` pulled the host's `venv/` and `node_modules/` into the image — Windows binaries in a Linux image | Both added, plus caches, `test.db` and `.env` so secrets cannot be baked into a layer |
| **Image size** | backend 687MB, frontend 218MB | **backend 448MB** (two-stage: gcc stays in the builder; runs as non-root), **frontend 74.4MB** (nginx instead of a Node runtime plus `npm install -g serve`) |
| **Production config** | None | `docker-compose.prod.yml`: datastores off the host network, no `:-default` so a missing secret stops the deploy, `ENVIRONMENT=production`, 4 workers, `read_only`, `no-new-privileges`, memory limits |
| **Redis security** | Unauthenticated | `--requirepass`; `NOAUTH Authentication required` verified |
| **`VITE_API_URL`** | Set as a runtime container env — silently ignored, because Vite inlines `import.meta.env` at build time | A build arg |

Also: the app refuses to start with `ENVIRONMENT=production` while
`JWT_SECRET` is still the value shipped in `.env.example`, and host ports are
parameterised so a machine already running Postgres or Redis needs no edit to
the compose file.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## 5. Tier 3C — Database performance

Full analysis, raw `EXPLAIN ANALYZE` output and reproduction steps:
[`docs/DB_PERFORMANCE.md`](docs/DB_PERFORMANCE.md).

**10,000 users / 1,000,000 todos**, medians of three warm runs:

| Query | Before | After | Speed-up | Buffers |
|---|---:|---:|---:|---|
| List page 1 (`LIMIT 20`) | 43.10 ms | **0.24 ms** | **182×** | 27,293 → 24 |
| Count for the user | 44.16 ms | **0.09 ms** | **475×** | 27,163 → 5 |
| Deep page (`OFFSET 100`) | 44.07 ms | **0.57 ms** | **77×** | 27,293 → 124 |

`Parallel Seq Scan` + `top-N heapsort` → a plain `Index Scan` that stops at
`LIMIT`; the count becomes an `Index Only Scan` that never touches the heap.

### Why not `(user_id, completed, created_at)`

The README suggests that order. It is measurably worse for the query this app
actually runs: an index satisfies an `ORDER BY` only from the columns
following an equality-constrained prefix, and the unfiltered list leaves
`completed` unconstrained — so `created_at` is only ordered *within* each
`completed` group and Postgres sorts anyway.

| Index available | Plan | Time | Size |
|---|---|---:|---:|
| `(user_id, completed, created_at)` | Bitmap Index Scan → **Sort** | 1.558 ms | 47 MB |
| `(user_id, created_at DESC, id DESC)` | Index Scan, no sort | **0.269 ms** | 56 MB |

It becomes the right index as soon as `?status=` filtering exists — at which
point the answer is **both**, not one replacing the other. Shipping it now
would be write and storage cost with no query to serve.

### Trade-offs

- **Write latency**: 50,000 bulk inserts, 3,870 ms with the index vs 1,656 ms
  without — 2.3× slower, about **+44 µs per row**. Irrelevant for `POST
  /todos` (one row, well under a tenth of a millisecond); it matters for bulk
  loads, where the move is drop → load → rebuild. `UPDATE` pays nothing unless
  it touches an indexed column, so toggling `completed` stays a HOT update.
- **Storage**: 56 MB on a 221 MB table (+25%), bought back by 27,000 buffers
  per request becoming 24.
- **Migration safety**: `CREATE INDEX CONCURRENTLY` inside an
  `autocommit_block()`, so the build takes `SHARE UPDATE EXCLUSIVE` instead of
  locking every read and write for its duration. `IF NOT EXISTS` plus a
  `DROP INDEX CONCURRENTLY IF EXISTS` downgrade, because a concurrent build
  can fail and leave an invalid index. SQLite has neither, so the migration
  branches on the dialect.

## 6. Git workflow

Branch `assessment/phi-long`, **27 commits**, Conventional Commits
throughout, each one scoped to a single concern.

Worth flagging: the first pass produced eight backend commits that each passed
the *final* test suite but not their own. Adding the Redis dependency to
`get_current_user` broke the old `MagicMock` double, so commits 2–7 failed the
tests as they stood at that commit. The history was reset and replayed with
the `conftest` change moved into the commit that needed it. Verified by
checking out each commit and running its own suite:

```
c19d6e5  fix(auth): enforce JWT expiration and access/refresh sep    9 passed
a6199d8  fix(auth): stop login enumeration and make logout actual    9 passed
fd99d74  fix(db): enforce unique user email                          9 passed
f4b7c97  fix(todos): scope every todo to its owner and keep parti    9 passed
f597664  fix(todos): scope the list cache per user and invalidate    9 passed
b153ae2  perf(todos): drop the N+1 owner lookup and order pages d    9 passed
d872f68  fix(config): restrict CORS origins and stop echoing SQL     9 passed
3e83119  test(backend): add regression coverage for the fixed bug   38 passed
```

## 7. Tier 4 — tags, filtering and bulk actions

Built after every mandatory tier was finished and verified, not alongside
them.

### Schema

`tags` is user-owned with a **unique index on `(user_id, lower(name))`**, so
"Work" and "work" are one tag for a user while two users may each have their
own "Work". Case-insensitivity lives in the database, not in a handler check:
two concurrent creates both pass a pre-check before either commits — the same
failure mode as the `users.email` fix in §1 (F-13), and tested the same way.

Deliberately **no separate index on `tags(user_id)`** even though the brief
lists one: the unique index already serves that lookup from its leading
column, so a second one would be write cost with nothing to show for it.

`todo_tags` has a composite primary key on `(todo_id, tag_id)` — that is what
makes a tag attachable once, and it indexes `todo_tags(todo_id)` for free. The
reverse lookup cannot use it, since `tag_id` is not the leading column, so
that gets its own index. Both FKs are `ON DELETE CASCADE`.

### API

```
GET    /api/v1/tags                           PATCH  /api/v1/todos/bulk-status
POST   /api/v1/tags                           POST   /api/v1/todos/{id}/tags
PATCH  /api/v1/tags/{id}                      DELETE /api/v1/todos/{id}/tags/{tagId}
DELETE /api/v1/tags/{id}
GET    /api/v1/todos?status=&tag_id=&keyword=&date_from=&date_to=&page=&page_size=
```

- **Ownership** is in the `WHERE` clause for tags exactly as it is for todos,
  so a user can neither touch another user's tag nor put one on their own
  todo. Filtering by someone else's `tag_id` returns an empty list, not their
  todos.
- **Keyword** searches title and description with LIKE wildcards escaped, so
  `50%` finds a literal percent sign instead of everything.
- **Dates** are whole UTC days, `date_to` inclusive — what picking a range in
  a date picker means.
- **`page_size`** is accepted as the brief names it; the existing `size` still
  works.
- **Bulk updates** run as one statement in the request's transaction, and are
  all-or-nothing: if any id is not the caller's, the request is rejected and
  nothing is written. Silently skipping ids would report a success that did
  not happen to the rows the caller asked about. Repeated ids are collapsed so
  the `updated` count stays honest. The route is declared before `/{todo_id}`
  so "bulk-status" is never parsed as an id — which is itself a test.

### Caching

The list cache key now covers **every filter**, not just owner and page. A key
that ignored a filter would serve the wrong rows to the same user: the
single-user version of the cross-user leak in F-03. The fingerprint is derived
from the same `TodoFilters` object the query is built from, so query and key
cannot drift apart, and is hashed only to bound key length.

Invalidation also fires on attach, detach, bulk update, and on tag **rename
and delete** — tags are embedded in every cached page, so renaming one makes
those pages stale even though no todo row moved.

### Frontend

Tag manager dialog (list/create/rename/delete with a colour picker), a filter
bar with keyword, status, tag, date range and "Clear filters", tag badges on
each row, and per-row selection driving a bulk-action bar.

- The keyword input is **debounced 300ms**, so typing stays instant while the
  query key — and therefore the request and its server-side cache entry — only
  moves once typing pauses.
- Query keys carry every filter, for the same reason the server's key does.
- Tag mutations invalidate the todo lists too, since tags are embedded in
  every todo payload.
- Selection is cleared only **after** the write lands: the server is
  all-or-nothing, so on failure nothing changed and the user should still have
  their selection to retry with.
- An empty *filtered* list says "No todos match these filters", not "No todos
  yet" — different situations calling for different actions.
- Both checkboxes on a row carry an explicit accessible name; "select for a
  bulk action" and "mark done" are not actions to confuse.

### Index

`(user_id, completed, created_at DESC, id DESC)` now ships **alongside** the
one in §5, because `?status=` finally gives it a query to serve. Not instead
of it: for the unfiltered list, `completed` between the filter and the sort
key still forces a sort. Built `CONCURRENTLY`, like the other.

### Tests

**47 backend tests** (`test_tags.py`, `test_todo_filters.py`) and **10 E2E
specs**. Beyond the scenarios the brief suggests: trimming and blank names,
non-hex colours, duplicates in every casing plus the constraint itself, two
users sharing a name, a stranger getting 404 on rename and delete, delete
removing the tag from todos without deleting them, idempotent attach,
detaching something not attached, each filter alone and all combined, `total`
reflecting the filter, filtered pagination staying disjoint, literal
wildcards, one cache entry per filter set, invalidation on all five write
paths, and bulk update verified to change **nothing** on either side when one
id is foreign.

## 8. Known limitations

Carried from [`docs/MANUAL_TEST_PLAN.md`](docs/MANUAL_TEST_PLAN.md) §6, since
they are the honest edges of this work:

1. **Logout revokes one access token, not the whole session.** The refresh
   token issued alongside it stays valid until used or expired. Revoking a
   whole token family needs a per-user generation counter.
2. **No rate limiting on login.** The generic error removes the enumeration
   oracle but not brute force. Redis-backed attempt counters per address and
   per IP are the follow-up.
3. **Tokens live in `localStorage`**, so any XSS reads them. Moving the
   refresh token to an httpOnly cookie is the standard fix and a larger change
   than this branch should carry.
4. **`OFFSET` still degrades on deep pages.** Keyset pagination is the fix and
   the shipped index already serves it, but it changes the API contract.
5. **Three UI cases are not automated yet** — DOM identity on delete, offline
   rollback, and the pagination controls. All three are cheap Playwright
   additions.
6. **The tag filter is not benchmarked.** It joins `todo_tags`, which is
   indexed both ways, but the numbers in `DB_PERFORMANCE.md` are for the plain
   and status-filtered lists.
7. **passlib 1.7.4 logs a trapped `bcrypt.__about__` error** on startup with
   bcrypt 4.x. Harmless — hashing works — but it is noise in the logs, and the
   real fix is to move off passlib.
8. **Chromium only**; no accessibility pass.

## 9. Reproducing everything

```bash
# Stack
cp .env.example .env
docker compose up -d --build

# Backend suite
cd backend && python -m venv venv && ./venv/Scripts/pip install -r requirements.txt
./venv/Scripts/python -m pytest tests/ -v          # 85 passed

# The same suite against the pre-fix code
cd .. && git checkout main -- backend/app backend/alembic && cd backend
./venv/Scripts/python -m pytest tests/test_auth_security.py tests/test_authorization.py \
                               tests/test_todo_updates.py tests/test_cache.py -q
# 22 failed, 7 passed
cd .. && git checkout HEAD -- backend && cd backend

# E2E
cd ../e2e && npm install && npx playwright install chromium
npx playwright test                                # 17 passed

# Benchmarks
docker compose exec -e SEED_USERS=10000 -e SEED_TODOS=1000000 backend python -m app.db.seed
docker compose exec postgres psql -U fabbi -d postgres
```
