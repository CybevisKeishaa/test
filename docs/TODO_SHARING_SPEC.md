# Technical Specification: Todo List Sharing

| | |
|---|---|
| **Status** | Proposed |
| **Author** | Phi Long |
| **Last updated** | 2026-09-17 |
| **Scope** | Backend + frontend, one release |

---

## 1. Overview & Objective

### 1.1 Feature summary

A user (the **owner**) can grant another registered user access to their todo
list as either a **viewer** (read-only) or an **editor** (read + write). The
owner can change a collaborator's role or revoke access at any time, and a
revocation takes effect on the very next request.

### 1.2 Problem statement

Todos today are strictly single-tenant: `todos.user_id` is the only access
rule, and every route filters on it. A pair or a small team that wants to work
from one list has no option but to share an account password, which destroys
attribution and makes the audit trail worthless.

### 1.3 Roles

| Role | Granted by | Read list | Create / edit / delete todos | Manage shares |
|---|---|---|---|---|
| **Owner** | implicit (creator) | yes | yes | yes |
| **Editor** | owner | yes | yes | no |
| **Viewer** | owner | yes | no | no |

There is no admin/superuser role. Sharing is **not transitive**: an editor
cannot re-share the list onwards.

### 1.4 Success criteria

- A viewer who opens a shared list sees exactly the owner's todos, and gets
  `403` on every write.
- A revoked collaborator's next request fails, with no cached-permission
  window.
- Existing single-user behaviour is unchanged and its regression suite keeps
  passing.

---

## 2. User Stories & Acceptance Criteria

### US-1: Owner shares their list

- **As an** owner
- **I want to** grant another user viewer or editor access to my todo list
- **So that** we can work from the same list without sharing credentials

**Acceptance criteria**

- [ ] `POST /api/v1/shares` with a registered email and a role creates the
      share and returns `201` with the share record.
- [ ] The grantee immediately sees the list under "Shared with me".
- [ ] Sharing with my own address is rejected with `422`.
- [ ] Sharing with an address that already has a share is rejected with `409`;
      the response names the existing share id so the client can `PATCH` it.
- [ ] A role outside `{viewer, editor}` is rejected with `422`.

### US-2: Collaborator works on a shared list

- **As a** collaborator
- **I want to** open a list that was shared with me
- **So that** I can follow or contribute to it

**Acceptance criteria**

- [ ] `GET /api/v1/shares/received` lists every list shared with me, with the
      owner's email and my role.
- [ ] `GET /api/v1/todos?owner_id={id}` returns that owner's todos when I hold
      any role on it, and `403` when I do not.
- [ ] As **editor**, create / update / delete on that owner's todos succeed and
      the resulting rows keep `todos.user_id = owner_id` — an editor's writes
      belong to the list, not to the editor.
- [ ] As **viewer**, every write returns `403` with
      `detail: "Read-only access to this list"`, and the UI hides the write
      affordances rather than relying on the error.

### US-3: Owner changes or revokes access

- **As an** owner
- **I want to** downgrade or revoke a collaborator
- **So that** access matches who should actually have it, right now

**Acceptance criteria**

- [ ] `PATCH /api/v1/shares/{share_id}` changes the role and returns `200`.
- [ ] `DELETE /api/v1/shares/{share_id}` returns `204`.
- [ ] The **next** request the revoked user makes fails — no TTL window during
      which the stale grant is still honoured (see §7.2).
- [ ] A revoked user's "Shared with me" list no longer contains the list.
- [ ] Only the owner may manage a share; anyone else gets `404` (see §6.2).

### US-4: Account deletion cleans up

- **As the** system
- **I want** shares to disappear with their user
- **So that** no grant outlives its owner or grantee

**Acceptance criteria**

- [ ] Deleting either user removes the share row (`ON DELETE CASCADE`).
- [ ] No orphan rows remain that reference a missing user.

---

## 3. Scope

### 3.1 In scope

- List-level sharing with two roles, one grant per (owner, grantee) pair.
- Share CRUD, "shared with me" listing, permission enforcement on todo routes.
- Cache correctness on grant, role change and revoke.
- Frontend: a list switcher, a share-management dialog, read-only rendering.

### 3.2 Out of scope

Deliberately excluded to keep the release small; each is a follow-up:

- **Per-todo sharing.** The unit is the whole list.
- **Invitations to unregistered addresses.** The grantee must already have an
  account. Email invitations need a token flow and deliverability work.
- **Transitive / re-sharing**, share links, and public lists.
- **Multiple lists per user.** Each user still has exactly one implicit list,
  identified by their user id. The data model is deliberately shaped so a
  future `lists` table can slot in (see §4.4).
- **Realtime push.** Collaborators see changes on their next fetch, not over a
  websocket.
- **Activity log / attribution UI.** `todos.updated_by` is added (§4.2) but
  nothing renders it yet.
- **Notifications** of any kind.

---

## 4. Database Design

### 4.1 New table: `todo_list_shares`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `UUID` | no | `gen_random_uuid()` | PK |
| `owner_id` | `UUID` | no | — | FK to `users(id)`, `ON DELETE CASCADE` |
| `grantee_id` | `UUID` | no | — | FK to `users(id)`, `ON DELETE CASCADE` |
| `role` | `share_role` | no | — | enum: `viewer`, `editor` |
| `created_at` | `TIMESTAMPTZ` | no | `now()` | |
| `updated_at` | `TIMESTAMPTZ` | no | `now()` | bumped on role change |

**Constraints**

```sql
CREATE TYPE share_role AS ENUM ('viewer', 'editor');

ALTER TABLE todo_list_shares
  ADD CONSTRAINT uq_share_owner_grantee UNIQUE (owner_id, grantee_id),
  ADD CONSTRAINT ck_share_not_self      CHECK (owner_id <> grantee_id);
```

- `uq_share_owner_grantee` is what actually makes duplicate invites
  impossible. The handler's "does a share already exist?" lookup is a nicer
  error message, not a guarantee: two concurrent invites both pass it before
  either commits. This is the same failure mode the `users.email` fix on this
  branch addressed.
- `ck_share_not_self` enforces US-1's self-share rule in the database, so it
  holds for the seed script and for manual SQL too, not only for the API.
- A Postgres `ENUM` over a free-text column: an invalid role becomes
  unrepresentable rather than something every read path must re-validate.

**Indexes**

| Index | Columns | Serves |
|---|---|---|
| `uq_share_owner_grantee` | `(owner_id, grantee_id)` | uniqueness; also "who can see my list", since `owner_id` leads |
| `ix_shares_grantee` | `(grantee_id)` | "which lists are shared with me" |

No index on `role`: with two values the planner will sequential-scan anyway.

### 4.2 Altered table: `todos`

| Column | Type | Null | Notes |
|---|---|---|---|
| `updated_by` | `UUID` | yes | FK to `users(id)`, `ON DELETE SET NULL` |

`user_id` keeps its meaning — **the owner of the list the todo belongs to** —
and is never set to an editor's id. `updated_by` records who last touched the
row. Nullable because every existing row predates the column, and
`ON DELETE SET NULL` so removing a collaborator does not delete list content.

### 4.3 Migration plan

1. `CREATE TYPE share_role`, then `CREATE TABLE todo_list_shares` with its
   constraints and indexes. New table, so no lock contention.
2. `ALTER TABLE todos ADD COLUMN updated_by UUID NULL` — metadata-only in
   Postgres 11+, no table rewrite, safe on a large `todos`.
3. `CREATE INDEX CONCURRENTLY` for `ix_shares_grantee` if the table is ever
   populated before this ships (it will not be, but the habit matters).

Backfill: none. Every existing todo is already owned by exactly one user and
that stays true.

Rollback: drop the table and the column. No data loss for pre-existing rows,
since nothing outside this feature reads either.

### 4.4 Forward compatibility

The share row points at `owner_id`, not at a `list_id`. When multiple lists
per user arrive, the migration is: create `lists`, give every user a default
list, add `list_id` to `todos` and to `todo_list_shares`, backfill both from
`owner_id` / `user_id`, then drop `owner_id`. This is deliberate — adding a
`lists` table now would be unused indirection in every query for the whole of
this release.

---

## 5. API Contracts

All routes require `Authorization: Bearer <access token>`. Errors use the
existing FastAPI shape, `{"detail": "..."}`.

### 5.1 Endpoints

| Method | Endpoint | Description | Who |
|---|---|---|---|
| `POST` | `/api/v1/shares` | Grant access to my list | owner |
| `GET` | `/api/v1/shares` | Shares I have granted | owner |
| `GET` | `/api/v1/shares/received` | Lists shared with me | grantee |
| `PATCH` | `/api/v1/shares/{share_id}` | Change a collaborator's role | owner |
| `DELETE` | `/api/v1/shares/{share_id}` | Revoke access | owner |

Existing todo routes gain an optional `owner_id`:

| Method | Endpoint | Change |
|---|---|---|
| `GET` | `/api/v1/todos?owner_id={uuid}` | Defaults to the caller. Any role required. |
| `POST` | `/api/v1/todos?owner_id={uuid}` | Editor or owner. Created row gets `user_id = owner_id`. |
| `GET` / `PUT` / `DELETE` | `/api/v1/todos/{todo_id}` | Resolved via the todo's own `user_id`; no `owner_id` parameter needed. |

### 5.2 `POST /api/v1/shares`

Request:

```json
{
  "email": "collaborator@example.com",
  "role": "editor"
}
```

`email` is a required `EmailStr`; `role` is required and must be `viewer` or
`editor`.

Response `201 Created`:

```json
{
  "id": "8f1c2b7e-0000-4000-8000-000000000001",
  "owner_id": "3a9e2b7e-0000-4000-8000-000000000002",
  "grantee": {
    "id": "b72d2b7e-0000-4000-8000-000000000003",
    "email": "collaborator@example.com"
  },
  "role": "editor",
  "created_at": "2026-09-17T09:12:44Z",
  "updated_at": "2026-09-17T09:12:44Z"
}
```

| Status | When | `detail` |
|---|---|---|
| `400` | grantee address has no account | `"No user with that email"` |
| `409` | share already exists | `"Already shared with this user"`, plus `share_id` |
| `422` | self-share, unknown role, malformed email | pydantic error body |
| `429` | rate limit exceeded (§6.5) | `"Too many share invitations"` |

### 5.3 `PATCH /api/v1/shares/{share_id}`

Request: `{ "role": "viewer" }`

`200` with the updated record; `404` if the share does not exist **or** the
caller is not its owner (§6.2).

### 5.4 `DELETE /api/v1/shares/{share_id}`

`204 No Content`. A second call returns `404`, which the UI treats as
"already revoked".

### 5.5 `GET /api/v1/shares/received`

```json
{
  "items": [
    {
      "share_id": "8f1c2b7e-0000-4000-8000-000000000001",
      "owner": {
        "id": "3a9e2b7e-0000-4000-8000-000000000002",
        "email": "owner@example.com"
      },
      "role": "viewer",
      "created_at": "2026-09-17T09:12:44Z"
    }
  ],
  "total": 1
}
```

### 5.6 Write rejection for viewers

```json
{ "detail": "Read-only access to this list" }
```

Returned as `403`, not `404`: the caller demonstrably knows the list exists,
since they can read it, so there is nothing left to conceal and a `404` would
be actively confusing.

---

## 6. Business Logic & Security

### 6.1 Permission resolution

One dependency resolves the caller's effective role, and every todo route
depends on it:

```
resolve_access(caller, owner_id) -> "owner" | "editor" | "viewer" | None

    if caller.id == owner_id:
        return "owner"
    share = lookup(owner_id, caller.id)
    return share.role if share else None
```

- Read routes require a non-`None` role.
- Write routes require `owner` or `editor`.
- **The owner stays in the SQL `WHERE` clause.** `get_todo_by_id(db, todo_id,
  owner_id)` keeps its current shape; only the value of `owner_id` changes,
  from "always the caller" to "the resolved list owner". Authorization must not
  become a post-load `if` on a row fetched by id alone — that is exactly the
  IDOR pattern this branch removed from all three todo routes.

### 6.2 Enumeration

Share-management routes return `404` rather than `403` when the caller is not
the owner: a `403` would confirm that `share_id` exists. This matches the
`404` the todo routes now return for a non-owner.

`POST /shares` is the deliberate exception. Reporting `400 "No user with that
email"` does reveal whether an address has an account, and there is no way to
offer "share with this person" without it. Accepted because the caller is
authenticated and rate-limited (§6.5), and because the alternative — silently
accepting invitations for addresses that may not exist — makes a typo
indistinguishable from success. **Revisit if invitation-by-email lands**, which
removes the need to answer the question at all.

### 6.3 Edge cases

| Case | Behaviour |
|---|---|
| Self-share | `422`. Enforced in the schema, in the handler, and by `ck_share_not_self`. |
| Duplicate invite | `409` naming the existing `share_id`. Deliberately not an idempotent upsert: silently changing an existing editor to viewer because someone re-sent an invite is a downgrade nobody asked for. |
| Concurrent duplicate invites | One wins; the loser catches `IntegrityError` and returns the same `409`. |
| Role changed mid-session | The next request uses the new role. In-flight requests complete under the role they resolved with — a window of one request, which is acceptable. |
| Revoked while a write is in flight | The write either commits (resolved before the revoke) or returns `403`. It cannot half-apply: each request is one transaction. |
| Two editors edit one todo | Last write wins, and `exclude_unset` means each only overwrites the fields it actually sent. See §6.4. |
| Owner deletes their account | Cascade removes shares and todos. Collaborators simply stop seeing the list. |
| Grantee deletes their account | Cascade removes the share. `todos.updated_by` becomes `NULL`. |
| Editor deletes a todo | Allowed. Deletion is a write, and withholding it makes "editor" a role nobody can explain. |
| `owner_id` points at a non-existent user | `403`, not `404` — same response as "no access", so the parameter cannot be used to probe for account ids. |

### 6.4 Concurrent updates

Last-write-wins per field is the shipped behaviour, and is adequate for a
two- or three-person list.

If lost updates become a real complaint, the fix is optimistic concurrency,
not locks: return `updated_at` as a weak `ETag`, accept `If-Match` on
`PUT /todos/{id}`, and answer `412 Precondition Failed` when the row has moved
on. That is purely additive — no schema change, since `updated_at` already
exists — which is why it is out of scope now rather than designed around now.

### 6.5 Rate limiting

`POST /api/v1/shares` is capped at 20 requests per hour per user. Without it
the endpoint is a usable "does this email have an account?" oracle at scale
(§6.2). Implemented with the existing Redis client: `INCR` on
`ratelimit:shares:{user_id}:{hour}` with a one-hour TTL.

---

## 7. Caching & Invalidation

### 7.1 The key change

Today the key is `todos:list:{user_id}:page={p}:size={s}`, where `user_id` is
the caller. That becomes wrong in one specific way: two different callers
viewing **the same shared list** must hit the same entry, because the cached
body depends on the list, not on the viewer.

The key is therefore rebased on the **owner**:

```
todos:list:{owner_id}:page={p}:size={s}
```

The viewer's role deliberately does **not** enter the key. The cached payload
is list data; whether the caller may write it is decided per request by
`resolve_access`, so a viewer and an editor can safely share one entry. Baking
the role into the key would duplicate every page per role for no benefit.

> Any per-viewer field in the response would break this. `user_email` is the
> list owner's for every row, so it is fine. If a `can_edit` flag is ever added
> to the list payload it must be attached **after** the cache read, never
> stored in it.

### 7.2 Permission cache

`resolve_access` runs on every todo request, so it is cached:

```
share:{owner_id}:{grantee_id} -> "viewer" | "editor" | "none"    TTL 300s
```

This is the entry that makes revocation dangerous: a 5-minute TTL would leave
a revoked collaborator with full access for up to five minutes. **Every share
mutation deletes the key synchronously, inside the same request that writes
the row**, before responding:

| Event | Invalidates |
|---|---|
| Grant | `share:{owner}:{grantee}` |
| Role change | `share:{owner}:{grantee}` |
| Revoke | `share:{owner}:{grantee}` |
| Grantee account deleted | `share:*:{grantee}` via SCAN |

Negative results are cached as `"none"` as well — otherwise every
unauthorised probe becomes a database query.

### 7.3 Invalidation on writes

Unchanged in shape, rebased on the owner: a write by **anyone** with access
drops `todos:list:{owner_id}:*` through the existing SCAN-based
`delete_pattern`. An editor's write has to invalidate the owner's cached
pages, which the old caller-scoped key could not express.

### 7.4 What is deliberately not cached

`GET /shares` and `GET /shares/received` are small, per-user and read rarely.
Caching them would add two more invalidation paths to get wrong, for no
measurable gain.

---

## 8. Frontend Notes

- A list switcher in the header: "My list" plus every entry from
  `/shares/received`.
- `owner_id` joins the react-query key:
  `["todos", { ownerId, page, size }]`. Omitting it would repeat the cache
  collision this branch just fixed, except across users rather than pages.
- The viewer role hides the create button, the checkbox and the row actions.
  The `403` stays as a backstop; the UI must not be the only thing enforcing
  it.
- Logout keeps clearing the whole react-query cache, which now matters more:
  the cache can hold another user's list.

---

## 9. Test Plan

**Backend**

- Owner grants viewer / editor; the grantee sees the list.
- Viewer write returns `403`; editor write returns `200` and `user_id` is
  still the owner's.
- Non-collaborator read returns `403`; an unknown `owner_id` also returns
  `403`, not `404`.
- Self-share returns `422`; duplicate returns `409`; the database rejects both
  independently of the handler.
- **Revoke, then immediately request** returns `403`, with no TTL window.
- An editor's write drops the owner's cached pages.
- Two viewers of one list hit a single cache entry (assert the store size).
- Cascade: deleting either user removes the share row.

**E2E**

- Owner shares with B, B sees the list, owner revokes, B's next action fails
  and the list disappears from "Shared with me".
- The existing cross-user isolation test must keep passing unchanged: a user
  with **no** share still sees nothing.

---

## 10. Open Questions

1. Should an editor be able to delete todos they did not create? Assumed yes
   (§6.3); cheap to restrict later, expensive to loosen.
2. Should there be a cap on collaborators per list? Not enforced; the rate
   limit bounds abuse.
3. Should `GET /todos` without `owner_id` return a merged view of every
   accessible list? Assumed no — one list at a time keeps pagination honest.
