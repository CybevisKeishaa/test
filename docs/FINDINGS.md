# Findings & Fixes

Every defect found in this codebase, what was wrong with it, and what was done
about it.

| | |
|---|---|
| **Author** | Phi Long |
| **Branch** | `assessment/phi-long` |
| **Date** | 2026-09-17 |
| **Total** | 35 findings, 35 fixed |

---

## How to read this

Each entry gives:

- **Location** — file and line **in the original code** (`main`), so the claim
  can be checked against what was actually there.
- **Why it is a problem** — the consequence, not a restatement of the code.
- **Fix** — what changed.
- **Proof** — the test that fails on `main` and passes here. Findings without
  a test are marked as such and say why.

**Severity** is impact if it is hit or exploited in production. It is not the
same as effort to fix: F-08 is one character.

Running the regression suite against the pre-fix code gives **22 of 29
failures** — see [Verifying these claims](#verifying-these-claims).

---

## Summary

### Code (F-01 – F-28)

| ID | Area | Severity | Summary |
|---|---|---|---|
| [F-01](#f-01--expired-tokens-never-expired) | Auth | **Critical** | JWT expiry was explicitly disabled |
| [F-02](#f-02--a-refresh-token-authenticated-any-request) | Auth | **Critical** | Refresh token worked as an access token |
| [F-03](#f-03--one-users-todo-list-was-served-to-everyone) | Cache | **Critical** | One global cache key for all users |
| [F-04](#f-04-f-05-f-06--idor-on-read-update-and-delete) | Authz | **Critical** | Any user could read any todo |
| [F-05](#f-04-f-05-f-06--idor-on-read-update-and-delete) | Authz | **Critical** | Any user could edit any todo |
| [F-06](#f-04-f-05-f-06--idor-on-read-update-and-delete) | Authz | **Critical** | Any user could delete any todo |
| [F-07](#f-07--logout-left-the-previous-users-data-in-the-browser) | Web | **Critical** | Logout left the react-query cache intact |
| [F-08](#f-08--a-completed-todo-could-never-be-reopened) | Logic | High | `completed=false` silently discarded |
| [F-09](#f-09--partial-updates-destroyed-data) | Logic | High | A partial update blanked unsent fields |
| [F-10](#f-10--nothing-invalidated-the-cache) | Cache | High | No write path touched Redis |
| [F-11](#f-11--login-was-an-account-enumeration-oracle) | Auth | High | 404 vs 401 revealed which emails exist |
| [F-12](#f-12--logout-did-nothing) | Auth | High | Logout returned success and no-op'd |
| [F-13](#f-13--usersemail-had-no-unique-constraint) | DB | High | Duplicate emails broke login for both |
| [F-14](#f-14--a-failed-login-reloaded-the-page) | Web | High | 401 interceptor ate the login error |
| [F-15](#f-15--paging-did-nothing) | Web | High | Query key ignored page and size |
| [F-16](#f-16--the-client-fetched-the-entire-table) | Web | High | `size=10000` by default |
| [F-17](#f-17--no-index-on-todos) | DB | High | Every list scanned the whole table |
| [F-18](#f-18--n1-query-on-the-todo-list) | Perf | Medium | One `SELECT` per row for one email |
| [F-19](#f-19--pagination-had-no-total-order) | DB | Medium | No `ORDER BY` with `OFFSET`/`LIMIT` |
| [F-20](#f-20--refresh-tokens-were-replayable-and-outlived-their-account) | Auth | Medium | Token reusable forever; deleted accounts still refreshed |
| [F-21](#f-21--cors-allowed-every-origin-with-credentials) | Sec | Medium | `allow_origins=["*"]` + credentials |
| [F-22](#f-22--no-password-length-bounds) | Auth | Medium | bcrypt truncated past 72 bytes |
| [F-23](#f-23--optimistic-updates-were-never-rolled-back) | Web | Medium | Snapshot taken, never restored |
| [F-24](#f-24--react-list-keyed-by-array-index) | Web | Medium | `key={index}` on a mutable list |
| [F-25](#f-25--the-refresh-endpoint-was-never-called) | Web | Medium | Every session died after 30 minutes |
| [F-26](#f-26--sql-echo-on-by-default) | Ops | Low | Row data printed to stdout |
| [F-27](#f-27--deprecated-redis-close) | Ops | Low | `close()` deprecated in redis-py 5 |
| [F-28](#f-28--password-rules-disagreed-across-the-stack) | Web | Low | Form allowed 6, API required 8 |

### Infrastructure (F-29 – F-35)

| ID | Area | Severity | Summary |
|---|---|---|---|
| [F-29](#f-29--the-backend-raced-postgres-on-a-cold-boot) | Docker | High | `depends_on` without a condition |
| [F-30](#f-30--no-dockerignore) | Docker | High | Host `venv/` and `node_modules/` copied into images |
| [F-31](#f-31--vite_api_url-was-set-as-a-runtime-variable) | Docker | High | Vite inlines at build time, so it was ignored |
| [F-32](#f-32--redis-was-unauthenticated) | Sec | Medium | No password on the cache |
| [F-33](#f-33--oversized-images) | Docker | Medium | 687MB backend, 218MB frontend |
| [F-34](#f-34--no-production-configuration) | Ops | Medium | Committed defaults would ship as-is |
| [F-35](#f-35--gitignore-swallowed-the-docs-directory) | Repo | Low | The required spec could not be committed |

---

## Critical

### F-01 · Expired tokens never expired

- **Location** `backend/app/core/security.py:56`
- **Severity** Critical

```python
payload = jwt.decode(
    token,
    settings.JWT_SECRET,
    algorithms=[settings.JWT_ALGORITHM],
    options={"verify_exp": False},   # <-- expiry disabled
)
```

**Why it is a problem.** Every access token ever issued stayed valid forever.
`ACCESS_TOKEN_EXPIRE_MINUTES` was decorative. A token pulled out of a log
file, a browser on a shared machine, or a proxy cache was a permanent
credential — there was no point at which it stopped working.

**Fix.** Removed the override; `jwt.decode` verifies `exp` by default.
`verify_token()` also gained an `expected_type` argument (see F-02) and access
tokens now carry a `jti` so they can be revoked (see F-12).

**Proof** `test_auth_security.py::test_expired_access_token_is_rejected`

---

### F-02 · A refresh token authenticated any request

- **Location** `backend/app/api/deps.py:21` (`get_current_user`)
- **Severity** Critical

The `type` claim was written into both token kinds and then never read.

**Why it is a problem.** The 7-day refresh token worked anywhere the
30-minute access token did. The short access-token lifetime — the entire point
of splitting the two — bought nothing, and a refresh token stored by a client
was in practice a week-long API key.

**Fix.** `verify_token(token, expected_type="access")` in `get_current_user`,
and `expected_type="refresh"` in `/auth/refresh`. A mismatch returns `None`,
so the route answers `401`.

**Proof** `test_refresh_token_cannot_be_used_as_access_token`,
`test_access_token_cannot_be_used_to_refresh`

---

### F-03 · One user's todo list was served to everyone

- **Location** `backend/app/api/v1/todos.py:37`
- **Severity** Critical

```python
cache_key = "todos:list"          # one key, every user
```

**Why it is a problem.** The worst bug in the codebase. Whichever user listed
their todos first populated that key, and for the next five minutes **every
other user received that same cached body** — someone else's todos, rendered
as their own.

What makes it particularly nasty: the SQL underneath was correctly filtered by
`user_id` the whole time. Reading the ORM layer, or the service, or the model,
shows nothing wrong. The breach lives entirely in the key.

**Fix.** The key carries the owner and the pagination window:
`todos:list:{user_id}:page={p}:size={s}`. After Tier 4 it carries every filter
too, derived from the same `TodoFilters` object the query is built from, so
the query and the key cannot drift apart.

**Proof** `test_cache.py::test_cached_list_is_not_served_across_users`
(asserts two separate Redis entries exist, not one shared),
`cross-user-isolation.spec.ts` (two real browser sessions)

---

### F-04, F-05, F-06 · IDOR on read, update and delete

- **Location** `backend/app/api/v1/todos.py:95`, `:114`, `:145`
- **Severity** Critical

```python
todo = await get_todo_by_id(db, todo_id)   # id only; current_user unused
if not todo:
    raise HTTPException(404)
# ... no ownership check anywhere below
```

**Why it is a problem.** All three handlers took `current_user` as a
dependency and then never compared it with the row. Any authenticated
account could read, edit or delete **any** other account's todo given its id —
and ids leak readily (shared links, logs, a previous response).

**Fix.** The owner moved into the SQL `WHERE` clause:

```python
async def get_todo_by_id(db, todo_id, user_id):
    return (await db.execute(
        select(Todo).where(Todo.id == todo_id, Todo.user_id == user_id)
    )).scalar_one_or_none()
```

This is deliberately not a post-load `if todo.user_id != current_user.id`. With
the owner in the query there is no code path that can *load* another user's
row, so a future handler cannot forget the check.

A miss returns **404, not 403**: answering "this exists but is not yours"
still confirms which ids are real.

**Proof** `test_authorization.py` — three tests, each also verifying the row is
genuinely untouched afterwards; plus API-level checks in
`cross-user-isolation.spec.ts`

---

### F-07 · Logout left the previous user's data in the browser

- **Location** `frontend/src/features/auth/hooks/useAuth.ts:23`
- **Severity** Critical

```js
logoutMutation.mutate(undefined, {
  onSuccess: () => navigate("/login"),      // tokens removed, cache untouched
});
```

**Why it is a problem.** react-query keys were `["currentUser"]` and
`["todos"]` — per query *name*, not per user. Removing the two localStorage
tokens did nothing to the in-memory cache, so the next person to sign in on
that browser was served the previous account's cached entries for the whole
5-minute `staleTime`: another user's todos rendered **without a single request
being made**. On a shared or kiosk machine this leaks outright.

**Fix.** Login and logout both clear the cached data. Logout does it from
`onSettled`, so a failed logout call cannot leave the session behind.

> A second, self-inflicted bug lived here briefly — see
> [Introduced and fixed during this work](#introduced-and-fixed-during-this-work).

**Proof** `cross-user-isolation.spec.ts` — "logging out clears the cached list
before the next account signs in", which switches accounts by client-side
navigation so a full page load cannot do the clearing for us

---

## High

### F-08 · A completed todo could never be reopened

- **Location** `backend/app/api/v1/todos.py:123`
- **Severity** High

```python
if todo_data.completed:          # truthiness, not "was it sent?"
    todo.completed = todo_data.completed
```

**Why it is a problem.** `False` is falsy. Un-ticking a todo sent
`completed: false`, the guard skipped the assignment, and the value never
reached the database. The checkbox appeared to work — the optimistic UI flipped
it — and then reverted on the next refetch. A finished todo could not be
reopened at all.

**Fix.** See F-09; both are fixed by the same change.

**Proof** `test_todo_updates.py::test_completed_can_be_set_back_to_false` —
toggles true, then false, then re-reads to confirm it persisted

---

### F-09 · Partial updates destroyed data

- **Location** `backend/app/api/v1/todos.py:121`
- **Severity** High

```python
update_data = todo_data.model_dump()        # no exclude_unset
```

**Why it is a problem.** `TodoUpdate` has three optional fields. Without
`exclude_unset`, pydantic materialises every absent one as `None`. A request
carrying only a new title produced `{"title": ..., "description": None,
"completed": None}` — so editing a title silently wiped the description.
Irreversible data loss on the most ordinary action in the app.

**Fix.** Apply `model_dump(exclude_unset=True)` as-is:

```python
update_data = todo_data.model_dump(exclude_unset=True)
updated_todo = await update_todo(db, todo, update_data)
```

A field that is sent is written — including `false`, which fixes F-08. A field
that is not sent is untouched. An explicit `null` still clears the column, so
"clear the description" remains expressible.

**Proof** `test_partial_update_preserves_untouched_fields`,
`test_partial_update_preserves_completed_flag`,
`test_description_can_be_cleared_explicitly`, plus a UI-level check in
`user-journey.spec.ts`

---

### F-10 · Nothing invalidated the cache

- **Location** `backend/app/api/v1/todos.py` — create, update and delete
- **Severity** High

**Why it is a problem.** `redis` was injected as a dependency into the update
and delete handlers and then never used; create did not even inject it. With a
300-second TTL, a newly created or edited todo did not appear in the list for
up to five minutes. The app looked broken in the most visible way possible.

**Fix.** Every write drops that user's cached pages:

```python
await invalidate_todo_list_cache(redis, current_user.id)
```

It uses `SCAN`, not `KEYS`, so invalidation never blocks the Redis event loop
on a large keyspace, and it is scoped to one user so nobody else's cached
pages are thrown away. After Tier 4 the same call fires on tag attach, detach,
bulk update, and on tag rename and delete.

**Proof** `test_cache.py` — four tests: create, update, delete, and that
invalidation is scoped to the writing user

---

### F-11 · Login was an account-enumeration oracle

- **Location** `backend/app/api/v1/auth.py:54-66`
- **Severity** High

```python
if not user:
    raise HTTPException(404, "User with this email not found")
if not verify_password(...):
    raise HTTPException(401, "Incorrect password")
```

**Why it is a problem.** Two different responses for two different failures.
Anyone could feed a list of addresses to `/auth/login` and learn exactly which
ones have an account — useful for targeted phishing, credential stuffing, and
simply for knowing who uses the service.

**Fix.** One shared error for both cases:

```python
if not user or not verify_password(user_data.password, user.hashed_password):
    raise INVALID_LOGIN          # 401 "Invalid email or password"
```

**Proof** `test_login_does_not_reveal_whether_email_exists` — asserts the two
responses are byte-identical, not merely both 401

---

### F-12 · Logout did nothing

- **Location** `backend/app/api/v1/auth.py:102`
- **Severity** High

```python
@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    return {"message": "Successfully logged out"}
```

**Why it is a problem.** It reported success and touched nothing. Combined
with F-01 (tokens never expire), "log out" on a shared machine left a
credential that worked forever. The endpoint was worse than absent: it told
the user they were safe.

**Fix.** The presented token's `jti` is blacklisted in Redis with a TTL equal
to the token's own remaining lifetime, so the blacklist cannot grow without
bound. `get_current_user` checks it on every request.

**Proof** `test_logout_revokes_the_access_token` — calls `/auth/me`, logs out,
then replays the *same* token and expects 401

---

### F-13 · `users.email` had no unique constraint

- **Location** `backend/app/models/user.py:21`
- **Severity** High

**Why it is a problem.** Two accounts could hold the same address. That is bad
on its own, but the specific failure is worse: `get_user_by_email` uses
`scalar_one_or_none()`, which **raises `MultipleResultsFound`** the moment a
duplicate exists — so a duplicate breaks login for *both* accounts with a 500.

The handler's "is this email taken?" lookup is not a guard. Two concurrent
registrations both pass it before either commits. Only a constraint is a
constraint.

There was also no index, so every login and registration sequential-scanned
`users`.

**Fix.** Unique index on `email`, added in migration `b1c2d3e4f5a6`. The
migration collapses any pre-existing duplicates first — keeping the oldest
account and re-pointing its todos — so the index build cannot abort against
live data. The handler also catches `IntegrityError` and returns the same
friendly 400 as the pre-check.

**Proof** `test_database_rejects_duplicate_emails` — inserts a duplicate
directly through the ORM and expects `IntegrityError`, so the test exercises
the constraint rather than the handler's pre-check

---

### F-14 · A failed login reloaded the page

- **Location** `frontend/src/lib/api.ts:30`
- **Severity** High

```js
if (error.response?.status === 401) {
  localStorage.removeItem("access_token");
  window.location.href = "/login";      // on EVERY 401
}
```

**Why it is a problem.** It fired on every 401 — including the one a failed
login legitimately returns. Typing a wrong password wiped storage and
hard-navigated to `/login`, reloading the page before the error toast could be
read. The user saw the form blank itself with no explanation.

**Fix.** 401s from `/auth/login`, `/auth/register` and `/auth/refresh` pass
through to the caller, which shows the message. Only a genuinely expired
session triggers the recovery path (see F-25).

**Proof** `user-journey.spec.ts` — "a wrong password shows an error instead of
reloading the page", asserting both the toast and that the URL did not move

---

### F-15 · Paging did nothing

- **Location** `frontend/src/features/todos/api/todos.ts:37`
- **Severity** High

```js
queryKey: ["todos"],                       // constant
queryFn: () => api.get("/todos", { params: { page, size } }),   // varies
```

**Why it is a problem.** The key did not include the parameters the request
varied by, so page 2's response overwrote page 1's cache entry under the same
key and was then read back as page 1. Combined with the server-side twin of
this bug (F-03), pagination could not work at all.

**Fix.** `["todos", { page, size }]`, and after Tier 4 every filter as well.

**Proof** `test_cache.py::test_cache_key_distinguishes_pages` — asserts the
two pages return disjoint id sets

---

### F-16 · The client fetched the entire table

- **Location** `frontend/src/features/todos/api/todos.ts:35`
- **Severity** High

```js
export function useTodos(page: number = 1, size: number = 10000) {
```

**Why it is a problem.** Ten thousand rows requested and rendered on every
visit, with no pagination controls anywhere in the UI. On the 1,000,000-row
dataset the assessment ships a seed for, this is a multi-megabyte response and
a frozen browser.

**Fix.** Page size 20 with real previous/next controls. The API caps `size` at
100, so a client cannot ask for the table even by accident.

**Proof** `test_todo_updates.py::test_oversized_page_size_is_rejected`

---

### F-17 · No index on `todos`

- **Location** `backend/app/models/todo.py` — nothing beyond the primary key
- **Severity** High

**Why it is a problem.** Both statements behind `GET /todos` sequential-scanned
the entire table to return twenty rows. Measured on 10,000 users and 1,000,000
todos: **43 ms** and **27,293 buffers** to produce one page, growing with every
todo *any* user creates.

**Fix.** `(user_id, created_at DESC, id DESC)`, built `CONCURRENTLY`.

| Query | Before | After | Speed-up |
|---|---:|---:|---:|
| List page 1 | 43.10 ms | 0.24 ms | **182×** |
| Count | 44.16 ms | 0.09 ms | **475×** |
| Deep page | 44.07 ms | 0.57 ms | **77×** |

Note this is **not** the `(user_id, completed, created_at)` the brief
suggests — with `completed` unconstrained between the filter and the sort key,
the unfiltered list still pays a sort. Measured: 1.558 ms against 0.269 ms.
That index shipped later, alongside this one, once Tier 4's `?status=` gave it
a query to serve.

**Proof** Raw `EXPLAIN ANALYZE` output and the reproduction steps are in
[`DB_PERFORMANCE.md`](DB_PERFORMANCE.md)

---

## Medium

### F-18 · N+1 query on the todo list

- **Location** `backend/app/api/v1/todos.py:49`
- **Severity** Medium

```python
for todo in todos:
    user_result = await db.execute(select(User).where(User.id == todo.user_id))
```

**Why it is a problem.** One round trip to `users` per row, purely to attach
an email — 20 extra queries per page, 100 at the page cap. Every row in the
result is already filtered on `user_id == current_user.id`, so every one of
those queries returned the same user the handler was holding.

**Fix.** Use `current_user.email`. No join, no eager load, no extra query.

**Proof** No dedicated test. It is a pure performance change with no
observable behaviour difference, and asserting on query counts would couple
the suite to the ORM's internals.

---

### F-19 · Pagination had no total order

- **Location** `backend/app/services/todo_service.py:31`
- **Severity** Medium

```python
query = select(Todo).where(Todo.user_id == user_id).offset(skip).limit(limit)
```

**Why it is a problem.** No `ORDER BY`. SQL makes no guarantee about row order
without one, so with `OFFSET`/`LIMIT` the same todo could appear on two pages
or on none. The bug is invisible on small data and shows up exactly when it
matters.

**Fix.** `ORDER BY created_at DESC, id DESC`. `id` is not decoration:
`created_at` is not unique, and ties would break arbitrarily, which is the
same bug in a smaller form.

**Proof** `test_todo_updates.py::test_todo_list_is_ordered_newest_first`

---

### F-20 · Refresh tokens were replayable and outlived their account

- **Location** `backend/app/api/v1/auth.py:84-99`
- **Severity** Medium

**Why it is a problem.** To be fair to the original: this endpoint *did* check
the `type` claim, and it is one of the seven tests that already passed on
`main`. Two other gaps remained.

It never confirmed the account still existed — it read `sub` straight out of
the payload and minted new tokens for it — so a deleted user's refresh token
kept issuing working access tokens indefinitely.

And the presented token stayed valid after use, so a leaked refresh token was
replayable for its whole lifetime. Combined with F-01, "whole lifetime" meant
forever, since the refresh token's own `exp` was not enforced either.

**Fix.** Re-checks the user, and rotates: the presented token's `jti` is
revoked on use, so it works exactly once.

**Proof** `test_refresh_token_is_rotated_on_use`,
`test_refresh_token_for_deleted_user_is_rejected`

---

### F-21 · CORS allowed every origin with credentials

- **Location** `backend/app/main.py:31`
- **Severity** Medium

```python
allow_origins=["*"],
allow_credentials=True,
```

**Why it is a problem.** Browsers reject this combination outright, so it did
not even work — but the intent behind it, trusting every origin on a
credentialed API, is precisely what CORS exists to prevent.

**Fix.** Origins come from `CORS_ORIGINS`, and a validator refuses a wildcard
at startup rather than letting it be configured back in. Methods and headers
narrowed to the ones actually used.

**Proof** Verified manually (test plan TC-I06): starting with `CORS_ORIGINS=*`
fails with a validation error naming the variable.

---

### F-22 · No password length bounds

- **Location** `backend/app/schemas/user.py:9`
- **Severity** Medium

```python
password: str        # no constraints at all
```

**Why it is a problem.** Two ends of the same gap. A one-character password
was accepted. And bcrypt **silently truncates at 72 bytes** — a longer
password was accepted, stored, and then only ever verified up to byte 72, so
the user believed they had protection they did not have.

**Fix.** 8 to 72 characters, enforced in the schema and mirrored in the
frontend (F-28).

**Proof** `test_password_shorter_than_minimum_is_rejected`,
`test_unverifiable_long_password_is_rejected`

---

### F-23 · Optimistic updates were never rolled back

- **Location** `frontend/src/features/todos/api/todos.ts:76`
- **Severity** Medium

```js
onMutate: async ({ id, data }) => {
  const previousTodos = queryClient.getQueryData([...]);
  // ... optimistic write ...
  return { previousTodos };      // returned, and never used by anything
},
onError: () => { toast.error("Failed to update todo"); },   // no rollback
```

**Why it is a problem.** The snapshot was taken and returned, which is half of
the react-query rollback pattern. Nothing restored it. A rejected update — such
as the 404 a non-owner now receives — left the optimistic change on screen
until an unrelated refetch happened to correct it. The user saw a change the
server had refused.

**Fix.** `onError` restores every snapshotted entry. It snapshots *all*
cached pages and filter sets, not one, because the mutation does not know
which list the item is currently displayed in.

**Proof** No automated test — covered as a manual case (TC-C09) and listed as
a gap in [`MANUAL_TEST_PLAN.md`](MANUAL_TEST_PLAN.md) §6. Reproducing it needs
the server to reject a write the client considers valid.

---

### F-24 · React list keyed by array index

- **Location** `frontend/src/features/todos/components/TodoList.tsx:42`
- **Severity** Medium

```jsx
{todos.map((todo, index) => (
  <TodoItem key={index} ... />
))}
```

**Why it is a problem.** With an index key React matches rows by position, not
identity. Deleting or reordering an item makes the next one reuse the departed
row's DOM node and component state, so a checkbox visibly slides onto the
wrong todo before the refetch corrects it. In a list whose whole purpose is
per-row state, this is the textbook case against index keys.

**Fix.** `key={todo.id}`. Also removed `TodoItem`'s `index` prop, which
nothing read.

**Proof** No automated test — listed as gap TC-C08. Asserting on DOM identity
across a delete is possible in Playwright but was not written.

---

### F-25 · The refresh endpoint was never called

- **Location** `frontend/src/lib/api.ts` — no refresh path existed
- **Severity** Medium

**Why it is a problem.** The backend implemented `/auth/refresh` and the login
response stored a refresh token, and nothing ever used it. Every session died
after 30 minutes, dumping the user on the login page mid-task with whatever
they were typing lost.

**Fix.** On a 401 from a non-auth endpoint the interceptor calls
`/auth/refresh` once and replays the original request. Concurrent 401s share a
single in-flight refresh — which matters now that refresh tokens rotate
(F-20), since parallel refreshes would invalidate each other. A `_retried`
flag prevents an infinite loop, and a failed refresh clears the session and
redirects.

**Proof** The refresh mechanics are covered by `test_refresh_token_is_rotated_on_use`.
The browser-side retry is manual case TC-T08, **not executed** — it needs a
build with a one-minute token lifetime.

---

## Low

### F-26 · SQL echo on by default

- **Location** `backend/app/core/config.py:9` — `DB_ECHO: bool = True`
- **Severity** Low

**Why it is a problem.** Every statement and its bound parameters printed to
stdout. That is row data in the logs — emails, todo contents — plus a real
throughput cost, in whatever environment nobody remembered to override it.

**Fix.** Defaults to `False`; opt in when debugging.

---

### F-27 · Deprecated Redis `close()`

- **Location** `backend/app/core/redis.py:19`
- **Severity** Low

**Fix.** `aclose()`, the supported form in redis-py 5.

---

### F-28 · Password rules disagreed across the stack

- **Location** `frontend/src/features/auth/schemas/auth.ts:5`
- **Severity** Low

**Why it is a problem.** The form accepted 6 characters where the API required
8 (after F-22). A form that passes its own validation and then returns a 422
the user cannot act on is worse than no client validation at all.

**Fix.** Bounds mirrored from the backend, with a comment naming the file they
mirror. The **login** form no longer imposes a length rule at all: it is not
the place to tell someone their existing password is too short, and doing so
leaks the policy to anyone who visits.

---

## Infrastructure

### F-29 · The backend raced Postgres on a cold boot

- **Location** `docker-compose.yml` — `depends_on: [postgres, redis]`
- **Severity** High

**Why it is a problem.** `depends_on` without a condition waits only for the
container to be *created*, not ready. On a cold `up`, `alembic upgrade head`
ran against a Postgres still initialising and the backend died. It restarted
into the same race. First-run experience: a crash loop.

**Fix.** Healthchecks on Postgres (`pg_isready`) and Redis (`redis-cli ping`),
with the backend on `condition: service_healthy` and the frontend waiting on
the backend's own healthcheck.

**Proof** Verified from empty volumes (`docker compose down -v`): services go
healthy in order and all four report `RestartCount=0`.

---

### F-30 · No `.dockerignore`

- **Location** neither `backend/` nor `frontend/` had one
- **Severity** High

**Why it is a problem.** `COPY . .` pulled in whatever was on the host —
including a `venv/` built for Windows being copied into a Linux image, where
it both bloats the image and shadows the interpreter the image installs. Also
`node_modules/`, caches, `test.db`, and `.env`, meaning **local secrets baked
into a layer** that anyone with the image can read.

**Fix.** `.dockerignore` for both services covering virtualenvs, node_modules,
caches, the test database, and `.env`.

---

### F-31 · `VITE_API_URL` was set as a runtime variable

- **Location** `docker-compose.yml` — `frontend.environment.VITE_API_URL`
- **Severity** High

**Why it is a problem.** Vite inlines `import.meta.env` at **build** time. A
runtime container environment variable has no effect whatsoever, so the
setting was silently ignored and the built bundle always used whatever was
baked in. Anyone deploying to a real API URL would find the frontend still
calling `localhost:8000`, with nothing in the config to suggest why.

**Fix.** Moved to a build `ARG`, passed through `build.args`.

---

### F-32 · Redis was unauthenticated

- **Location** `docker-compose.yml` — `image: redis:7`, no command
- **Severity** Medium

**Why it is a problem.** Redis accepts commands from anything that can reach
the port, and here it held session and todo data. Combined with the published
host port, anything on the machine could read or flush it.

**Fix.** `--requirepass`, with the password carried in `REDIS_URL`. The
production overlay also takes the port off the host network entirely.

**Proof** Verified manually (TC-I02): `redis-cli ping` without auth returns
`NOAUTH Authentication required`.

---

### F-33 · Oversized images

- **Location** `backend/Dockerfile`, `frontend/Dockerfile`
- **Severity** Medium

**Why it is a problem.** The backend was single-stage, so `gcc` and the build
headers shipped in the final image — larger attack surface and slower pulls —
and it ran as **root**. The frontend shipped an entire Node runtime plus a
global `npm install -g serve` to serve static files.

**Fix.**

| Image | Before | After | How |
|---|---:|---:|---|
| backend | 687 MB | **448 MB** | Two-stage: only the populated virtualenv is copied forward. Runs as an unprivileged user. |
| frontend | 218 MB | **74.4 MB** | nginx instead of Node + `serve`. `nginx.conf` supplies the SPA fallback `serve -s` was providing. |

---

### F-34 · No production configuration

- **Location** — nothing existed
- **Severity** Medium

**Why it is a problem.** One compose file with committed defaults for every
secret, datastore ports published to the host, and a single-worker uvicorn.
Deploying it as-is would ship `JWT_SECRET=super-secret-key-change-in-production`
to production, and the file gives no signal that this is wrong.

**Fix.** `docker-compose.prod.yml`: datastores off the host network, **no
`:-default` anywhere** so a missing secret stops the deploy instead of
silently using the committed one, four uvicorn workers, `read_only`,
`no-new-privileges`, and memory limits. Separately, the app now refuses to
start with `ENVIRONMENT=production` while `JWT_SECRET` is still the shipped
value.

**Proof** TC-I04 and TC-I05, both verified.

---

### F-35 · `.gitignore` swallowed the `docs/` directory

- **Location** `.gitignore` — a bare `docs/` rule
- **Severity** Low

**Why it is a problem.** The assessment requires a specification at
`docs/TODO_SHARING_SPEC.md`. The rule would have silently excluded it from
every commit — the file would exist locally, `git status` would show nothing,
and the submission would simply be missing a graded deliverable.

**Fix.** Removed the blanket rule; the interviewer-only
`docs/ANSWER_KEY.md` line stays. Tool caches and Playwright output are ignored
instead.

---

## Introduced and fixed during this work

Two defects were mine, not inherited. They are listed because the commits are
in the history and because how they were found is the point.

### W-01 · Clearing the query cache from inside a mutation

- **Commit** `baa45b5`

`useLogin`/`useRegister` called `queryClient.clear()` inside `mutationFn`.
`clear()` empties the **mutation** cache as well as the query cache, and doing
that from within a mutation's own lifecycle can drop that mutation's
observers — so `onSuccess`, which stores the tokens and navigates, sometimes
never ran. Registration would appear to do nothing.

Fixed by using `removeQueries()` (queries only) and moving it to `onSuccess`,
so a mistyped password no longer wipes the cache of whoever is still signed
in.

### W-02 · A race in the E2E suite

- **Commit** `37911bc`

The tenant-switch spec clicked "Sign up" and filled the form immediately. Both
`/login` and `/register` render a field labelled "Email", so the fill could
land in the login form React was mid-way through unmounting: the register form
stayed empty, zod blocked the submit, and **no request was ever sent**.

Found by instrumenting the page rather than guessing — the diagnostic run
logged no `POST /auth/register` at all on a failing attempt, which ruled out
the application immediately. Fixed by asserting the URL and waiting for
"Confirm Password", a field only the register page has.

---

## Known and not fixed

Honest edges. Each is a deliberate stopping point, not an oversight.

1. **Logout revokes one access token, not the whole session.** The refresh
   token issued alongside it stays valid until used or expired. Revoking a
   token *family* needs a per-user generation counter.
2. **No rate limiting on login.** F-11 removes the enumeration oracle but not
   brute force. Redis-backed attempt counters per address and per IP are the
   follow-up.
3. **Tokens live in `localStorage`**, so any XSS reads them. Moving the
   refresh token to an httpOnly cookie is the standard fix and a larger change
   than this branch should carry.
4. **`OFFSET` still degrades on deep pages.** Keyset pagination is the fix and
   the shipped index already serves it, but it changes the API contract.
5. **passlib 1.7.4 logs a trapped `bcrypt.__about__` error** on startup with
   bcrypt 4.x. Harmless — hashing works — but it is noise, and the real fix is
   moving off passlib.
6. **Three UI cases are not automated** — F-23 rollback, F-24 DOM identity,
   and the pagination controls.
7. **Chromium only**; no accessibility pass.

---

## Verifying these claims

Nothing here should be taken on trust. The regression suite runs against the
pre-fix code:

```bash
cd backend
python -m venv venv && ./venv/Scripts/pip install -r requirements.txt

# On this branch
./venv/Scripts/python -m pytest tests/ -q                    # 85 passed

# The same tests against the original code
cd .. && git checkout main -- backend/app backend/alembic && cd backend
./venv/Scripts/python -m pytest tests/test_auth_security.py \
    tests/test_authorization.py tests/test_todo_updates.py \
    tests/test_cache.py -q                                   # 22 failed, 7 passed
cd .. && git checkout HEAD -- backend
```

The seven that pass on `main` cover behaviour that was already correct; they
are there as guards, not as evidence.

End-to-end:

```bash
docker compose up -d --build
cd e2e && npm install && npx playwright install chromium
npx playwright test                                          # 17 passed
```

Benchmarks, with the full `EXPLAIN ANALYZE` output pasted verbatim, are in
[`DB_PERFORMANCE.md`](DB_PERFORMANCE.md).
