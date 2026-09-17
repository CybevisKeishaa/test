# Manual Test Plan: Auth, Authorization, Todo CRUD & Caching

| | |
|---|---|
| **Author** | Phi Long |
| **Branch under test** | `assessment/phi-long` |
| **Last executed** | 2026-09-17 |

---

## 1. Scope & Objective

Verify the behaviour of the fixed defects and guard against regression across
authentication, authorization, todo CRUD and the Redis cache layer.

**In scope**: registration, login, token lifetime, logout, todo CRUD,
cross-user data isolation, cache correctness, pagination.

**Out of scope**: performance and load (covered by
[`docs/DB_PERFORMANCE.md`](DB_PERFORMANCE.md)), visual/responsive design,
browser-compatibility beyond Chromium.

---

## 2. Test Environment & Prerequisites

| | |
|---|---|
| Frontend | `http://localhost:3000` |
| Backend | `http://localhost:8000` (docs at `/docs`) |
| Stack | `docker compose up -d --build` |
| Browser | Chromium (latest) |

Two accounts are needed. Register them through the UI before starting:

| Alias | Email | Password |
|---|---|---|
| User A | `user_a@test.com` | `Password@123` |
| User B | `user_b@test.com` | `Password@123` |

A third identity, the seeded demo account (`demo@test.com` / `Demo@123`), is
available after `docker compose exec backend python -m app.db.seed`.

> Passwords must be at least 8 characters — the old 6-character minimum in the
> register form did not match the API and produced an unactionable 422.

**Tools for the API-level cases**: `curl`, or the Swagger UI at `/docs`.

---

## 3. Legend

**Priority** — how soon it must work. **Severity** — how bad it is when it
does not.

| Status | Meaning |
|---|---|
| Pass | Executed, expected result observed |
| Pass (auto) | Covered by an automated test; the referenced test is the evidence |
| Not executed | Documented for a future cycle |

---

## 4. Test Case Matrix

### 4.1 Authentication

| TC ID | Scenario | Preconditions | Steps | Expected result | Priority / Severity | Actual | Status |
|---|---|---|---|---|---|---|---|
| TC-A01 | Register a new account | Email not in use | 1. Open `/register`<br>2. Enter a fresh email + `Password@123` twice<br>3. Submit | `201`, tokens stored, redirected to the todo list, header shows the email | High / Blocker | As expected | Pass (auto: `test_auth.py::test_register_success`) |
| TC-A02 | Register with an address that already exists | TC-A01 done | Repeat TC-A01 with the same email | `400 "Email already registered"`, shown as a toast, no second account created | High / Major | As expected | Pass (auto: `test_auth_security.py::test_duplicate_email_registration_is_rejected`) |
| TC-A03 | Duplicate address cannot be created by racing the check | Account exists | Insert a second `users` row with the same email directly in the DB | `IntegrityError` — the unique index rejects it | Medium / Major | As expected | Pass (auto: `test_auth_security.py::test_database_rejects_duplicate_emails`) |
| TC-A04 | Password below the minimum | — | Register with `abc` | `422`, form shows "Password must be at least 8 characters", no request on an invalid form | Medium / Minor | As expected | Pass (auto: `test_auth_security.py::test_password_shorter_than_minimum_is_rejected`) |
| TC-A05 | Password longer than bcrypt can verify | — | Register with a 100-character password | `422` rather than a silently truncated 72-byte password | Low / Major | As expected | Pass (auto: `test_auth_security.py::test_unverifiable_long_password_is_rejected`) |
| TC-A06 | Mismatched confirmation | — | Register with differing password / confirm | Inline "Passwords don't match", no request sent | Medium / Minor | As expected | Not executed |
| TC-A07 | Login with correct credentials | User A exists | Enter A's email + password, submit | `200`, redirected to the list, A's todos shown | High / Blocker | As expected | Pass (auto: `test_auth.py::test_login_success`) |
| TC-A08 | **Login with a wrong password does not reveal the account** | User A exists | 1. Login as A with a wrong password<br>2. Login with an address that has no account | **Both** return `401` with the identical body `{"detail": "Invalid email or password"}` | High / Security | Identical responses | Pass (auto: `test_auth_security.py::test_login_does_not_reveal_whether_email_exists`) |
| TC-A09 | **A failed login shows its error instead of reloading** | User A exists | Login as A with a wrong password and watch the page | Toast "Invalid email or password" stays visible; the page does **not** reload and the URL stays `/login` | High / Major | As expected | Pass (auto: `user-journey.spec.ts`) |
| TC-A10 | `/auth/me` returns the signed-in user | Logged in | `GET /api/v1/auth/me` with the access token | `200` with that user's id, email, created_at — never another user's | High / Blocker | As expected | Pass (auto: `test_auth.py::test_get_current_user`) |
| TC-A11 | Request without a token | — | `GET /api/v1/todos` with no `Authorization` header | `403`, no data | High / Security | As expected | Pass (auto: `test_authorization.py::test_unauthenticated_requests_are_rejected`) |

### 4.2 Tokens & Session

| TC ID | Scenario | Preconditions | Steps | Expected result | Priority / Severity | Actual | Status |
|---|---|---|---|---|---|---|---|
| TC-T01 | **An expired access token is rejected** | User exists | Mint a token with a past `exp`, call `/auth/me` | `401`. (Before the fix, `verify_exp: False` meant every token lived forever.) | High / Critical | `401` | Pass (auto: `test_auth_security.py::test_expired_access_token_is_rejected`) |
| TC-T02 | A token signed with a different key is rejected | User exists | Sign a token with `not-the-real-secret`, call `/auth/me` | `401` | High / Critical | `401` | Pass (auto: `test_auth_security.py::test_token_signed_with_another_secret_is_rejected`) |
| TC-T03 | **A refresh token cannot be used as an access token** | Registered | Send the refresh token as the bearer on `/auth/me` | `401` — the `type` claim must match | High / Critical | `401` | Pass (auto: `test_auth_security.py::test_refresh_token_cannot_be_used_as_access_token`) |
| TC-T04 | An access token cannot be used to refresh | Registered | `POST /auth/refresh` with the access token | `401` | Medium / Major | `401` | Pass (auto: `test_auth_security.py::test_access_token_cannot_be_used_to_refresh`) |
| TC-T05 | **Logout revokes the presented token** | Logged in | 1. `GET /auth/me` → `200`<br>2. `POST /auth/logout`<br>3. Replay step 1 with the *same* token | Step 3 returns `401`. (Before the fix, logout returned success and did nothing.) | High / Critical | `401` | Pass (auto: `test_auth_security.py::test_logout_revokes_the_access_token`) |
| TC-T06 | A refresh token is single-use | Registered | Call `/auth/refresh` twice with the same token | First `200`, second `401` | Medium / Major | As expected | Pass (auto: `test_auth_security.py::test_refresh_token_is_rotated_on_use`) |
| TC-T07 | A refresh token stops working once the account is gone | Registered | Delete the user, then refresh | `401` | Medium / Major | `401` | Pass (auto: `test_auth_security.py::test_refresh_token_for_deleted_user_is_rejected`) |
| TC-T08 | An expired session is renewed silently | Logged in, `ACCESS_TOKEN_EXPIRE_MINUTES=1` | Wait for expiry, then click a todo | The request is retried after a transparent refresh; the user is **not** bounced to `/login` | Medium / Major | — | Not executed (needs a 1-minute token build) |
| TC-T09 | Protected route with no token | Logged out | Navigate to `/` | Redirected to `/login` | High / Major | As expected | Pass (auto: `cross-user-isolation.spec.ts`) |

### 4.3 Authorization & Data Isolation

| TC ID | Scenario | Preconditions | Steps | Expected result | Priority / Severity | Actual | Status |
|---|---|---|---|---|---|---|---|
| TC-Z01 | **A cannot read B's todo** | B owns todo `X` | As A, `GET /api/v1/todos/X` | `404`, and the response body contains none of B's content | High / Critical | `404` | Pass (auto: `test_authorization.py::test_user_cannot_read_another_users_todo`) |
| TC-Z02 | **A cannot update B's todo** | B owns todo `X` | As A, `PUT /api/v1/todos/X` with a new title | `404`, and re-reading as B shows the original title | High / Critical | `404`, unchanged | Pass (auto: `test_authorization.py::test_user_cannot_update_another_users_todo`) |
| TC-Z03 | **A cannot delete B's todo** | B owns todo `X` | As A, `DELETE /api/v1/todos/X` | `404`, and B can still read `X` | High / Critical | `404`, still present | Pass (auto: `test_authorization.py::test_user_cannot_delete_another_users_todo`) |
| TC-Z04 | The list contains only the caller's rows | A and B each own todos | As B, `GET /api/v1/todos` | Only B's todos; `total` counts only B's | High / Critical | As expected | Pass (auto: `test_authorization.py::test_todo_list_only_contains_own_todos`) |
| TC-Z05 | **B does not see A's todos in the UI** | A has a private todo; separate browser sessions | 1. A logs in, creates "Alice private todo"<br>2. B logs in in another context<br>3. Compare | B sees "No todos yet". A's title appears nowhere, including after a reload | High / Critical | Empty for B | Pass (auto: `cross-user-isolation.spec.ts`) |
| TC-Z06 | **Logging out clears the cached list** | A logged in on this browser with todos | 1. A logs out<br>2. B registers/logs in on the same browser | B's list is empty. A's todos must not flash up from the client cache | High / Critical | Empty for B | Pass (auto: `cross-user-isolation.spec.ts`) |

### 4.4 Todo CRUD

| TC ID | Scenario | Preconditions | Steps | Expected result | Priority / Severity | Actual | Status |
|---|---|---|---|---|---|---|---|
| TC-C01 | Create a todo | Logged in | Add Todo → title + description → Create | `201`; the row appears at the **top** of the list; toast confirms | High / Blocker | As expected | Pass (auto: `test_todos.py::test_create_todo`) |
| TC-C02 | Create with an empty title | Logged in | Submit with a blank title | Inline "Title is required"; no request sent | Medium / Minor | As expected | Not executed |
| TC-C03 | **Un-complete a completed todo** | A completed todo exists | 1. Un-tick the checkbox<br>2. Reload | It stays un-ticked. (Before the fix the falsy `false` was discarded and a completed todo could never be reopened.) | High / Major | Stays un-ticked | Pass (auto: `test_todo_updates.py::test_completed_can_be_set_back_to_false`) |
| TC-C04 | **A title-only edit keeps the description** | Todo has both fields | Edit the title only, save | The description is unchanged. (Before the fix a partial update blanked every unsent field.) | High / Major | Preserved | Pass (auto: `test_todo_updates.py::test_partial_update_preserves_untouched_fields`) |
| TC-C05 | A title-only edit keeps the completed flag | Todo is completed | Rename it | It is still completed | Medium / Major | Preserved | Pass (auto: `test_todo_updates.py::test_partial_update_preserves_completed_flag`) |
| TC-C06 | An explicit null still clears the description | Todo has a description | `PUT` with `{"description": null}` | Description becomes `null`; title untouched | Low / Minor | As expected | Pass (auto: `test_todo_updates.py::test_description_can_be_cleared_explicitly`) |
| TC-C07 | Delete a todo | A todo exists | Click the bin icon | `204`; it disappears; toast confirms; it stays gone after reload | High / Major | As expected | Pass (auto: `test_todos.py::test_delete_todo`) |
| TC-C08 | **Deleting the right row** | ≥3 todos, some completed | Delete the middle one | Exactly that one goes. No neighbouring row inherits its checkbox state. (`key={index}` used to reuse the DOM node.) | Medium / Major | — | Not executed |
| TC-C09 | A failed update rolls back | Logged in | Stop the backend, toggle a todo | The toggle reverts and an error toast appears — the UI does not keep showing a change the server rejected | Medium / Major | — | Not executed |
| TC-C10 | Newest first | ≥3 todos created in sequence | Open the list | Ordered by `created_at DESC` — newest at the top, stable across reloads | Medium / Major | As expected | Pass (auto: `test_todo_updates.py::test_todo_list_is_ordered_newest_first`) |

### 4.5 Pagination & Caching

| TC ID | Scenario | Preconditions | Steps | Expected result | Priority / Severity | Actual | Status |
|---|---|---|---|---|---|---|---|
| TC-P01 | Page size is capped | Logged in | `GET /api/v1/todos?size=10000` | `422`. One request cannot pull the whole table | Medium / Major | `422` | Pass (auto: `test_todo_updates.py::test_oversized_page_size_is_rejected`) |
| TC-P02 | **Page 2 is not page 1** | ≥3 todos, `size=2` | Request page 1, then page 2 | Different rows, no overlap. (One shared cache key used to return page 1 for both.) | High / Major | Disjoint | Pass (auto: `test_cache.py::test_cache_key_distinguishes_pages`) |
| TC-P03 | Pagination controls | >20 todos | Use the next/previous buttons | The page indicator updates and the rows change; previous is disabled on page 1, next on the last page | Medium / Minor | — | Not executed |
| TC-P04 | **The cache is not shared between users** | A has todos, B has none | 1. A lists (populates the cache)<br>2. B lists | B gets an empty list. Two separate Redis entries exist, not one | High / Critical | Empty; 2 keys | Pass (auto: `test_cache.py::test_cached_list_is_not_served_across_users`) |
| TC-P05 | **Create invalidates the cache** | Cache warm | Create a todo, list again | The new todo appears immediately, not after the 5-minute TTL | High / Major | Immediate | Pass (auto: `test_cache.py::test_create_invalidates_cached_list`) |
| TC-P06 | **Update invalidates the cache** | Cache warm | Rename a todo, list again | The new title appears immediately | High / Major | Immediate | Pass (auto: `test_cache.py::test_update_invalidates_cached_list`) |
| TC-P07 | **Delete invalidates the cache** | Cache warm | Delete a todo, list again | It is gone and `total` drops | High / Major | Immediate | Pass (auto: `test_cache.py::test_delete_invalidates_cached_list`) |
| TC-P08 | Invalidation is scoped to the writer | A and B both cached | B creates a todo | Only B's cached pages are dropped; A's stay | Medium / Minor | As expected | Pass (auto: `test_cache.py::test_invalidation_is_scoped_to_the_writing_user`) |

### 4.6 Infrastructure

| TC ID | Scenario | Preconditions | Steps | Expected result | Priority / Severity | Actual | Status |
|---|---|---|---|---|---|---|---|
| TC-I01 | **Cold boot** | No volumes (`docker compose down -v`) | `docker compose up --build` | The backend waits for Postgres and Redis to report healthy, then migrates and serves. No crash-restart loop | High / Blocker | Clean start | Pass |
| TC-I02 | Redis requires a password | Stack up | `redis-cli -h localhost -p 6379 ping` with no auth | `NOAUTH Authentication required` | Medium / Security | As expected | Pass |
| TC-I03 | A deep link works after refresh | Stack up | Open `http://localhost:3000/register` directly | The app renders — nginx falls back to `index.html` rather than returning 404 | Medium / Major | Renders | Pass |
| TC-I04 | Production compose refuses to start without secrets | — | `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` with no env | Fails naming the missing variable rather than falling back to the committed default | Medium / Security | Fails as intended | Pass |
| TC-I05 | The app refuses the shipped JWT secret in production | — | Start with `ENVIRONMENT=production` and the default `JWT_SECRET` | Startup fails with a message naming `JWT_SECRET` | Medium / Security | Fails as intended | Pass |
| TC-I06 | CORS rejects a wildcard | — | Set `CORS_ORIGINS=*` and start | Startup fails with a validation error | Low / Security | Fails as intended | Pass |

---

## 5. Execution Summary

| Suite | Result |
|---|---|
| Backend (`pytest tests/ -v`) | 38 passed |
| E2E (`npx playwright test`) | 7 passed |
| Manual / infrastructure | TC-I01 … TC-I06 executed |

---

## 6. Defects & Known Limitations

Defects found during review are listed in full in the pull-request
description. All of them are fixed on this branch.

**Not covered by this cycle:**

1. **TC-T08 (silent refresh)** — verifying it end to end needs a build with a
   1-minute access-token lifetime. The refresh path itself is covered by
   TC-T06 and by `test_refresh_token_is_rotated_on_use`; only the browser-side
   retry is unproven.
2. **TC-C08, TC-C09, TC-P03** — DOM-identity, offline-rollback and pagination
   controls are not automated yet. All three are cheap Playwright additions
   and are the first thing I would add next.
3. **Logout revokes one access token, not the whole session.** The refresh
   token issued alongside it stays valid until used or expired. Revoking the
   whole token family needs a per-user token generation counter; out of scope
   here, and worth doing before any real deployment.
4. **No rate limiting on login.** Nothing throttles password guessing. The
   generic error (TC-A08) removes the enumeration oracle but not the brute
   force. Recommended follow-up: Redis-backed attempt counters per address and
   per IP.
5. **Tokens live in `localStorage`**, so any XSS reads them. Moving the
   refresh token to an httpOnly cookie is the standard fix and a larger change
   than this branch should carry.
6. **No accessibility or cross-browser pass.** E2E runs Chromium only.
