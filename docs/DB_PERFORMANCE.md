# Database Performance: Indexing `todos`

| | |
|---|---|
| **Author** | Phi Long |
| **Date** | 2026-09-17 |
| **Dataset** | 10,000 users / 1,000,000 todos (`SEED_USERS=10000 SEED_TODOS=1000000`) |
| **Engine** | PostgreSQL 16 (`postgres:16-alpine`) in Docker, default `shared_buffers` |
| **Migrations** | `c2d3e4f5a6b7_index_todos_user_created.py`, `d3e4f5a6b7c8_add_tags_and_todo_tags.py` |

---

## 1. Summary

`todos` had no index beyond its primary key, so every list request
sequential-scanned a million rows. One composite index removes that
completely.

| Query | Before | After | Speed-up | Buffers before → after |
|---|---:|---:|---:|---|
| Q1 — list page 1 (`LIMIT 20`) | 43.10 ms | **0.24 ms** | **182×** | 27,293 → 24 |
| Q2 — count for the user | 44.16 ms | **0.09 ms** | **475×** | 27,163 → 5 |
| Q3 — deep page (`OFFSET 100`) | 44.07 ms | **0.57 ms** | **77×** | 27,293 → 124 |

Medians of three warm runs each. The plan changes from `Parallel Seq Scan` +
`top-N heapsort` to a plain `Index Scan` that stops at `LIMIT`, and Q2 becomes
an `Index Only Scan`.

Cost: **56 MB** of index on a 221 MB table, and roughly **+44 µs per inserted
row** (§6).

---

## 2. Reproducing

```bash
docker compose up -d --build
docker compose exec -e SEED_USERS=10000 -e SEED_TODOS=1000000 backend python -m app.db.seed
docker compose exec postgres psql -U fabbi -d postgres

-- pick the user with the most todos
SELECT user_id FROM todos GROUP BY user_id ORDER BY count(*) DESC LIMIT 1;
```

The user used below is `71415063-d865-4156-8f81-b9f7f04d2757`, with 141 todos
— an ordinary account, not an outlier. `ANALYZE todos;` was run before each
measurement so the planner had fresh statistics in both states.

---

## 3. The queries

These are the two statements `GET /api/v1/todos` actually issues, from
`app/services/todo_service.py`:

```sql
-- Q1: the page itself
SELECT id, title, description, completed, user_id, created_at, updated_at
FROM todos
WHERE user_id = $1
ORDER BY created_at DESC, id DESC
OFFSET $2 LIMIT $3;

-- Q2: the total for the pagination footer
SELECT count(*) FROM todos WHERE user_id = $1;
```

`GET /todos/{id}` is served by the primary key and was never a problem.

> The `ORDER BY` is itself part of the fix on this branch — the original query
> had no `ORDER BY` at all, which meant `OFFSET`/`LIMIT` could return the same
> row on two pages or skip it entirely.

---

## 4. Before: no index

```
########## Q1 LIST PAGE 1 ##########
 Limit (actual time=34.941..38.961 rows=20 loops=1)
   Buffers: shared hit=11166 read=16127
   ->  Gather Merge (actual time=34.939..38.958 rows=20 loops=1)
         Workers Planned: 2
         Workers Launched: 2
         Buffers: shared hit=11166 read=16127
         ->  Sort (actual time=30.903..30.905 rows=16 loops=3)
               Sort Key: created_at DESC, id DESC
               Sort Method: top-N heapsort  Memory: 35kB
               Buffers: shared hit=11166 read=16127
               ->  Parallel Seq Scan on todos (actual time=1.557..30.391 rows=47 loops=3)
                     Buffers: shared hit=11036 read=16127
 Planning Time: 1.896 ms
 Execution Time: 39.421 ms

########## Q2 COUNT ##########
 Finalize Aggregate (actual time=33.327..37.148 rows=1 loops=1)
   Buffers: shared hit=11132 read=16031
   ->  Gather (actual time=33.173..37.142 rows=3 loops=1)
         Workers Planned: 2
         Workers Launched: 2
         ->  Partial Aggregate (actual time=29.552..29.553 rows=1 loops=3)
               ->  Parallel Seq Scan on todos (actual time=1.054..29.536 rows=47 loops=3)
                     Buffers: shared hit=11132 read=16031
 Planning Time: 0.108 ms
 Execution Time: 37.192 ms

########## Q3 DEEP PAGE (offset 100) ##########
 Limit (actual time=33.247..37.219 rows=20 loops=1)
   ->  Gather Merge (actual time=33.203..37.211 rows=120 loops=1)
         ->  Sort (actual time=29.707..29.709 rows=43 loops=3)
               Sort Key: created_at DESC, id DESC
               Sort Method: quicksort  Memory: 32kB
               ->  Parallel Seq Scan on todos (actual time=1.296..29.310 rows=47 loops=3)
                     Buffers: shared hit=11228 read=15935
 Planning Time: 0.066 ms
 Execution Time: 37.252 ms
```

Warm repeats: Q1 43.10 / 46.36 ms, Q2 44.16 / 48.66 ms, Q3 44.12 / 44.07 ms.

**What this says.** To return 20 rows Postgres reads all 1,000,000, across
three parallel workers, then sorts the 141 that survive the filter. The work
is proportional to the size of the whole table, so it grows with every todo
any user creates — 27,000 buffers touched to produce 20 rows. It also burns
two extra worker backends per request, which is throughput the rest of the
API does not get.

---

## 5. After: `(user_id, created_at DESC, id DESC)`

```sql
CREATE INDEX CONCURRENTLY ix_todos_user_id_created_at
    ON todos (user_id, created_at DESC, id DESC);
```

```
########## Q1 LIST PAGE 1 ##########
 Limit (actual time=0.055..0.164 rows=20 loops=1)
   Buffers: shared hit=24
   ->  Index Scan using ix_todos_user_id_created_at on todos (actual time=0.054..0.162 rows=20 loops=1)
         Buffers: shared hit=24
 Planning Time: 1.531 ms
 Execution Time: 0.237 ms

########## Q2 COUNT ##########
 Aggregate (actual time=0.097..0.098 rows=1 loops=1)
   Buffers: shared hit=5
   ->  Index Only Scan using ix_todos_user_id_created_at on todos (actual time=0.069..0.088 rows=141 loops=1)
         Buffers: shared hit=5
 Planning Time: 0.103 ms
 Execution Time: 0.125 ms

########## Q3 DEEP PAGE (offset 100) ##########
 Limit (actual time=0.671..0.784 rows=20 loops=1)
   Buffers: shared hit=57 read=67
   ->  Index Scan using ix_todos_user_id_created_at on todos (actual time=0.026..0.778 rows=120 loops=1)
 Planning Time: 0.037 ms
 Execution Time: 0.807 ms
```

Warm repeats: Q1 0.243 / 0.208 ms, Q2 0.093 / 0.088 ms, Q3 0.545 / 0.572 ms.

**What changed.**

- **No `Sort` node.** The index is already in `created_at DESC, id DESC`
  order within each `user_id`, so the plan reads 20 entries and stops.
- **No parallel workers.** The query is now cheap enough that the planner does
  not bother, freeing those backends.
- **Q2 is an `Index Only Scan`** — it never touches the heap, because
  `count(*)` needs nothing the index does not already hold. 5 buffers.
- **Cost is now proportional to the page, not the table.** Q1 stays ~0.2 ms
  whether the table holds a million rows or a hundred million.

---

## 6. Trade-offs

### 6.1 Write latency

50,000 rows inserted in one statement, same session, measured with and
without the index (the index is dropped inside a transaction that is then
rolled back, so the comparison is on identical data):

| | Time | Per row |
|---|---:|---:|
| With `ix_todos_user_id_created_at` | 3,870 ms | 77 µs |
| Without it | 1,656 ms | 33 µs |

Bulk insert is **2.3× slower**; each row costs about **44 µs more**. For the
API this is irrelevant — `POST /todos` inserts one row, so the added cost is
well under a tenth of a millisecond against a request that already spends
milliseconds on network and JSON. It matters for the seed script and for any
future bulk import, where the right move is to drop the index, load, and
rebuild.

`UPDATE` pays the cost only when it touches a column the index contains.
Editing a `title` moves nothing in either index, so Postgres can use a HOT
update and skip them both. Toggling `completed` is free for this index, but
does move an entry in the status index added later in section 7 -- one more
reason that index is worth having only once a query actually needs it.

### 6.2 Storage

| | Size |
|---|---:|
| `todos` table | 221 MB |
| `todos_pkey` | 38 MB |
| `ix_todos_user_id_created_at` | 56 MB |

+25% on top of the table. Bought back immediately in reduced I/O: 27,000
buffers per list request down to 24.

The index is wider than the alternative in §7 because it carries `id`. That
third column is not decoration — without it `created_at` ties break
arbitrarily and pagination stops being stable, which is the bug the `ORDER BY`
was added to fix in the first place.

### 6.3 Migration safety

A plain `CREATE INDEX` takes an `ACCESS EXCLUSIVE` lock for the whole build.
On this dataset that is several seconds during which every read and write to
`todos` blocks; on a real production table it is an outage.

The migration therefore uses `CREATE INDEX CONCURRENTLY`, which takes only a
`SHARE UPDATE EXCLUSIVE` lock and lets reads and writes continue. Two
consequences are handled explicitly:

- **It cannot run inside a transaction**, and Alembic wraps each migration in
  one. The migration opens an `autocommit_block()` around the statement.
- **It can fail and leave an invalid index behind**, which is why the
  statement is `IF NOT EXISTS` and the downgrade is
  `DROP INDEX CONCURRENTLY IF EXISTS`. If a build fails, drop the invalid
  index and re-run; nothing else is affected.

SQLite (the test suite) has neither `CONCURRENTLY` nor a reason to care, so
the migration branches on the dialect and creates a plain index there.

---

## 7. Why not `(user_id, completed, created_at)`

The README suggests that column order. It is measurably worse for the query
this application actually runs, and the reason is the middle column.

An index can only satisfy an `ORDER BY` from the columns that follow an
equality-constrained prefix. `WHERE user_id = $1` pins the first column, but
`completed` is left unconstrained by the list query — so the index's ordering
within a user is *by completed first*, and `created_at` is only ordered inside
each `completed` group. Postgres must therefore read all the matching entries
and sort them anyway.

Measured, with each index available in isolation on the same data:

```
-- only (user_id, completed, created_at DESC)
   ->  Sort (actual time=1.393..1.394 rows=20 loops=1)
         Sort Key: created_at DESC, id DESC
         Sort Method: top-N heapsort  Memory: 29kB
               ->  Bitmap Index Scan on ix_alt_user_completed_created (actual time=0.525..0.525 rows=141 loops=1)
 Execution Time: 1.558 ms

-- only (user_id, created_at DESC, id DESC)
   ->  Index Scan using ix_todos_user_id_created_at on todos (actual time=0.052..0.182 rows=20 loops=1)
 Execution Time: 0.269 ms
```

| | Plan | Time | Size |
|---|---|---:|---:|
| `(user_id, completed, created_at)` | Bitmap Index Scan → **Sort** | 1.558 ms | 47 MB |
| `(user_id, created_at DESC, id DESC)` | Index Scan, no sort | **0.269 ms** | 56 MB |

Both beat a sequential scan by a wide margin, so the README's suggestion is
not wrong — it is just 5.8× slower here and still pays for a sort whose cost
grows with how many todos the user owns.

**It now ships as well.** Tier 4 added `?status=`, so
`WHERE user_id = $1 AND completed = $2` pins both leading columns, `created_at`
then satisfies the `ORDER BY`, and the filtered plan is sort-free. Migration
`d3e4f5a6b7c8` adds `(user_id, completed, created_at DESC, id DESC)`
**alongside** the index above, not instead of it: each serves a query the other
cannot, and the unfiltered list is still the common case. Had the status filter
never arrived, that index would have stayed out — an index with no query to
serve is pure write and storage cost.

The measurements above were taken with each index available on its own, so they
show what the column order does rather than which index the planner happens to
prefer when both exist.

---

## 8. Not addressed here

1. **`OFFSET` degrades on deep pages.** Q3 at offset 100 is already 2.4×
   Q1, because `OFFSET n` still walks and discards `n` entries. At offset
   100,000 that is a real cost. The fix is keyset pagination —
   `WHERE (created_at, id) < ($last_created, $last_id)` — which this same
   index serves perfectly. It changes the API contract, so it belongs in its
   own change.
2. **`count(*)` on every request.** Cheap now (0.09 ms), but it is still a
   second query per page. For a user with a very large list, returning an
   estimate or only "has next page" would drop it entirely.
3. **The tag filter is not benchmarked here.** It joins `todo_tags`, which is
   indexed in both directions (composite primary key on `(todo_id, tag_id)`,
   plus `ix_todo_tags_tag_id` for the reverse lookup), but the numbers above
   are for the plain and status-filtered lists. Worth measuring once there is
   a realistic volume of tagged rows to measure against.
4. **`users.email`** got its index in `b1c2d3e4f5a6` — added for the unique
   constraint, and it also removes a sequential scan from every login. `tags`
   is indexed on `(user_id, lower(name))` for the same two reasons.
5. **`DB_ECHO` defaulted to `True`**, printing every statement and its bound
   values to stdout. That was a throughput cost on top of the missing index,
   and is now off by default.
